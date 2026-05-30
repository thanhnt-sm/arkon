"""
LM Studio async client wrapper — primary surface for load/unload/predict.

Strategy:
  1. At construction, attempt ``import lmstudio``.
  2. If available: use the Python SDK (sync calls wrapped in asyncio.to_thread).
  3. If ImportError: fall back to ``LMSRestClient`` (pure httpx, no extra dep).

The mode selected is logged once at INFO level.  Auth tokens are NEVER logged.

CORS / host.docker.internal note:
  LM Studio v0.4.x has a known issue (GitHub lmstudio-ai/lms#189) where
  host.docker.internal:1234 may not respond correctly.  Workaround: set
  LM Studio to listen on 0.0.0.0 and use the explicit Docker host IP, or use
  --network host on Linux.  REST fallback uses the same host string unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

import pydantic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def _sdk_api_host(host: str) -> str:
    """Normalize HTTP base URLs to the host:port form expected by lmstudio SDK."""
    value = host.strip().rstrip("/")
    if "://" in value:
        parsed = urlparse(value)
        return parsed.netloc or parsed.path.split("/", 1)[0]
    return value.split("/", 1)[0]


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class BusyError(Exception):
    """Raised when unload is attempted while one or more predict calls are inflight."""


# ---------------------------------------------------------------------------
# Pydantic config models
# ---------------------------------------------------------------------------


class LoadOptions(pydantic.BaseModel):
    """
    Programmable options passed to LM Studio when loading a model.

    Fields that exist only in the Python SDK (e.g. ttl_seconds, gpu_ratio)
    are silently dropped by the REST client when it cannot map them.
    NOT programmable via API: K/V quantization (UI-only), tokenizer settings.
    """

    context_length: int = 16384
    gpu_ratio: Optional[float] = None  # 0.0–1.0 fraction of layers on GPU
    flash_attention: Optional[bool] = None
    kv_cache_gpu_offload: Optional[bool] = None
    eval_batch_size: Optional[int] = None
    ttl_seconds: Optional[int] = None  # SDK-only: auto-unload after N idle seconds


class SamplingParams(pydantic.BaseModel):
    """Per-request sampling parameters sent alongside messages."""

    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    repeat_penalty: Optional[float] = None
    max_tokens: Optional[int] = None
    seed: Optional[int] = None
    response_format_json: bool = False


# ---------------------------------------------------------------------------
# Protocol — used for dependency injection / mocking in tests
# ---------------------------------------------------------------------------


@runtime_checkable
class LMSClientProtocol(Protocol):
    """Structural interface for LMSClient — enables mocking without subclassing."""

    async def load(
        self,
        model_id: str,
        load_options: LoadOptions,
        timeout_s: Optional[float] = None,
    ) -> str: ...

    async def unload(self, instance_id: str) -> None: ...

    async def list_loaded(self) -> list[str]: ...

    async def health(self) -> bool: ...

    async def predict(
        self,
        instance_id: str,
        messages: list[dict],
        sampling: SamplingParams,
        timeout_s: Optional[float] = None,
    ) -> str: ...


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class LMSClient:
    """
    Async client for LM Studio model lifecycle management.

    Preferred backend is the ``lmstudio`` Python SDK (v1.5+).  If the package
    is not installed, the client transparently falls back to the httpx REST
    implementation (``LMSRestClient``).

    All public methods are async.  SDK calls (sync) are dispatched via
    ``asyncio.to_thread`` to avoid blocking the event loop.

    Concurrency safety:
      - ``_inflight[instance_id]`` tracks in-progress predict calls.
      - ``_lock`` (asyncio.Lock) serialises mutations to ``_inflight``.
      - ``unload()`` raises ``BusyError`` when ``_inflight[instance_id] > 0``.
    """

    def __init__(
        self,
        host: str,
        auth_token: str = "",
        default_timeout_s: float = 120.0,
    ) -> None:
        self._host = host
        # Store auth_token without ever logging its value
        self._auth_token = auth_token
        self._default_timeout_s = default_timeout_s
        self._sdk_host = _sdk_api_host(host)

        self._inflight: dict[str, int] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

        from app.ai.local_orchestrator.lms_client_rest import LMSRestClient

        self._rest = LMSRestClient(
            host=host,
            auth_token=auth_token,
            default_timeout_s=default_timeout_s,
        )

        # Detect backend at construction — no network call, no DB touch
        try:
            import lmstudio as _lms  # noqa: F401 — presence check only

            self._mode = "sdk"
            self._sdk_module = _lms
            logger.info("LMSClient: using lmstudio SDK backend (host=%s)", host)
        except ImportError:
            self._mode = "rest"
            logger.info("LMSClient: lmstudio SDK not installed — using REST fallback (host=%s)", host)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _timeout(self, override: Optional[float]) -> float:
        return override if override is not None else self._default_timeout_s

    @asynccontextmanager
    async def _inflight_context(self, instance_id: str):
        """Async context manager that increments/decrements the inflight counter."""
        async with self._lock:
            self._inflight[instance_id] = self._inflight.get(instance_id, 0) + 1
        try:
            yield
        finally:
            async with self._lock:
                count = self._inflight.get(instance_id, 1) - 1
                self._inflight[instance_id] = max(count, 0)

    # ------------------------------------------------------------------
    # SDK helpers (called inside asyncio.to_thread)
    # ------------------------------------------------------------------

    def _sdk_load_sync(
        self,
        model_id: str,
        load_options: LoadOptions,
        timeout_s: float,
    ) -> str:
        """Synchronous SDK load — must run in a thread."""
        lms = self._sdk_module
        lms.set_sync_api_timeout(timeout_s)
        client = lms.Client(api_host=self._sdk_host)
        for loaded in client.llm.list_loaded():
            loaded_model_id = getattr(loaded, "identifier", None) or getattr(loaded, "instance_id", None)
            if str(loaded_model_id) == model_id:
                logger.info("load skipped: model already loaded: %s", model_id)
                return model_id
            if hasattr(loaded, "get_info"):
                try:
                    info = loaded.get_info()
                    loaded_model_id = (
                        getattr(info, "model_key", None)
                        or getattr(info, "identifier", None)
                        or loaded_model_id
                    )
                except Exception:
                    pass
            if str(loaded_model_id) == model_id:
                logger.info("load skipped: model already loaded: %s", model_id)
                return model_id
        config: dict = {
            "contextLength": load_options.context_length,
        }
        if load_options.gpu_ratio is not None:
            config["gpu"] = {"ratio": load_options.gpu_ratio}
        if load_options.eval_batch_size is not None:
            config["evalBatchSize"] = load_options.eval_batch_size
        if load_options.flash_attention is not None:
            config["flashAttention"] = load_options.flash_attention
        if load_options.kv_cache_gpu_offload is not None:
            config["offloadKVCacheToGpu"] = load_options.kv_cache_gpu_offload
        kwargs: dict = {"config": config}
        if load_options.ttl_seconds is not None:
            kwargs["ttl"] = load_options.ttl_seconds
        client.llm.load_new_instance(model_id, **kwargs)
        # Keep the model key as the runtime identifier. The OpenAI-compatible
        # predict endpoint accepts model keys, and this avoids SDK-generated
        # instance aliases leaking into REST chat calls.
        return model_id

    def _sdk_unload_sync(self, instance_id: str) -> None:
        """Synchronous SDK unload — must run in a thread."""
        lms = self._sdk_module
        client = lms.Client(api_host=self._sdk_host)
        client.llm.unload(instance_id)

    def _sdk_list_loaded_sync(self) -> list[str]:
        """Synchronous SDK list — must run in a thread."""
        lms = self._sdk_module
        client = lms.Client(api_host=self._sdk_host)
        loaded = client.llm.list_loaded()
        ids: list[str] = []
        for model in loaded:
            model_id = getattr(model, "identifier", None) or getattr(model, "instance_id", None)
            if not model_id and hasattr(model, "get_info"):
                try:
                    info = model.get_info()
                    model_id = (
                        getattr(info, "model_key", None)
                        or getattr(info, "identifier", None)
                        or getattr(info, "instance_reference", None)
                    )
                except Exception:
                    model_id = None
            if model_id:
                ids.append(str(model_id))
        return ids

    def _sdk_health_sync(self) -> bool:
        """Synchronous SDK health ping — must run in a thread."""
        try:
            lms = self._sdk_module
            lms.set_sync_api_timeout(5)
            client = lms.Client(api_host=self._sdk_host)
            client.llm.list_loaded()
            return True
        except Exception as exc:
            logger.debug("SDK health check failed: %s", exc)
            return False

    def _sdk_predict_sync(
        self,
        instance_id: str,
        messages: list[dict],
        sampling: SamplingParams,
        timeout_s: float,
    ) -> str:
        """Synchronous SDK predict — must run in a thread."""
        lms = self._sdk_module
        lms.set_sync_api_timeout(timeout_s)
        client = lms.Client(api_host=self._sdk_host)
        handle = client.llm.model(instance_id)
        predict_opts: dict = {}
        if sampling.temperature is not None:
            predict_opts["temperature"] = sampling.temperature
        if sampling.top_p is not None:
            predict_opts["topPSampling"] = sampling.top_p
        if sampling.top_k is not None:
            predict_opts["topKSampling"] = sampling.top_k
        if sampling.min_p is not None:
            predict_opts["minPSampling"] = sampling.min_p
        if sampling.repeat_penalty is not None:
            predict_opts["repeatPenalty"] = sampling.repeat_penalty
        if sampling.max_tokens is not None:
            predict_opts["maxTokens"] = sampling.max_tokens
        if sampling.seed is not None:
            predict_opts["seed"] = sampling.seed
        result = handle.respond(messages, config=predict_opts)
        return str(result)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True,
    )
    async def load(
        self,
        model_id: str,
        load_options: LoadOptions,
        timeout_s: Optional[float] = None,
    ) -> str:
        """
        Load a model and return its instance_id.

        Retried up to 3 times with exponential back-off on TimeoutError /
        ConnectionError.  Other exceptions propagate immediately.
        """
        effective_timeout = self._timeout(timeout_s)
        logger.debug("load: model=%s timeout=%.0fs mode=%s", model_id, effective_timeout, self._mode)

        if self._mode == "sdk":
            instance_id = await asyncio.to_thread(
                self._sdk_load_sync, model_id, load_options, effective_timeout
            )
        else:
            instance_id = await self._rest.load(model_id, load_options, effective_timeout)

        logger.info("load complete: instance_id=%s", instance_id)
        return instance_id

    async def unload(self, instance_id: str) -> None:
        """
        Unload a model instance.

        Raises ``BusyError`` if any predict calls are still inflight for this
        instance.  Check is done under the asyncio.Lock to avoid TOCTOU races.
        """
        async with self._lock:
            if self._inflight.get(instance_id, 0) > 0:
                raise BusyError(
                    f"Cannot unload {instance_id!r}: "
                    f"{self._inflight[instance_id]} predict call(s) still inflight."
                )

        logger.debug("unload: instance_id=%s", instance_id)
        if self._mode == "sdk":
            await asyncio.to_thread(self._sdk_unload_sync, instance_id)
        else:
            await self._rest.unload(instance_id)

        # Clean up inflight slot — entry may not exist if model was never predicted
        async with self._lock:
            self._inflight.pop(instance_id, None)
        logger.info("unload complete: instance_id=%s", instance_id)

    async def list_loaded(self) -> list[str]:
        """Return list of currently loaded model instance_ids."""
        if self._mode == "sdk":
            return await asyncio.to_thread(self._sdk_list_loaded_sync)
        return await self._rest.list_loaded()

    async def health(self) -> bool:
        """
        Single health ping — no retry.

        Returns True if LM Studio is reachable and responding, False otherwise.
        Never raises.
        """
        if self._mode == "sdk":
            return await asyncio.to_thread(self._sdk_health_sync)
        return await self._rest.health()

    async def predict(
        self,
        instance_id: str,
        messages: list[dict],
        sampling: SamplingParams,
        timeout_s: Optional[float] = None,
    ) -> str:
        """
        Run chat inference and return the assistant message content.

        Inflight counter for ``instance_id`` is incremented before the call
        and decremented in a ``finally`` block — safe even on exception.
        """
        effective_timeout = self._timeout(timeout_s)
        logger.debug("predict: instance_id=%s messages=%d", instance_id, len(messages))

        async with self._inflight_context(instance_id):
            if self._mode == "sdk":
                result = await self._rest.predict(
                    instance_id, messages, sampling, effective_timeout
                )
            else:
                result = await self._rest.predict(
                    instance_id, messages, sampling, effective_timeout
                )

        return result
