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
import signal
import subprocess
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

    async def force_unload_all(
        self,
        wait_s: float = 30.0,
        kill_on_timeout: bool = True,
    ) -> dict:
        """
        Unload every loaded model and wait for the LM Studio llmworker process
        to fully release system RAM.

        Background: The LM Studio SDK ``unload()`` call tells LM Studio to
        release the model, but the underlying llmworker subprocess (the Node.js
        process that actually holds GPU/CPU pages for the model weights) may
        keep its RSS for up to 30 seconds while macOS reclaims pages.  If a
        new ``load()`` is attempted before reclamation completes, LM Studio's
        own guardrails reject it with an "insufficient system resources" error.

        This method:
          1. Lists all currently loaded model instances.
          2. Calls ``unload()`` on each one.
          3. Polls (1 s interval) the llmworker process RSS until it drops
             below ``RAM_FREE_THRESHOLD_MB`` or ``wait_s`` elapses.
          4. If still alive after ``wait_s`` and ``kill_on_timeout=True``,
             sends SIGKILL to the worker and waits 2 s for OS reclaim.

        Args:
            wait_s: Maximum seconds to wait for voluntary RAM release.
            kill_on_timeout: Send SIGKILL to llmworker if wait expires.

        Returns:
            dict with keys:
              - unloaded (list[str]): model ids that were unloaded
              - worker_pid (int | None): llmworker PID found
              - ram_released (bool): True if RAM dropped below threshold
              - killed (bool): True if SIGKILL was sent
        """
        RAM_FREE_THRESHOLD_MB = 500  # RSS below this → fully released
        POLL_INTERVAL_S = 1.0

        result: dict = {
            "unloaded": [],
            "worker_pid": None,
            "ram_released": False,
            "killed": False,
        }

        # Step 1 — enumerate loaded instances
        try:
            loaded_ids = await self.list_loaded()
        except Exception as exc:
            logger.warning("force_unload_all: list_loaded failed: %s", exc)
            loaded_ids = []

        # Step 2 — unload each
        for iid in loaded_ids:
            try:
                await self.unload(iid)
                result["unloaded"].append(iid)
                logger.info("force_unload_all: unloaded %s", iid)
            except BusyError:
                logger.warning("force_unload_all: %s is busy, skipping", iid)
            except Exception as exc:
                logger.warning("force_unload_all: unload %s failed: %s", iid, exc)

        # Step 3 — find llmworker PID and poll RSS
        worker_pid = await asyncio.to_thread(self._find_llmworker_pid)
        result["worker_pid"] = worker_pid

        if worker_pid is None:
            logger.info("force_unload_all: no llmworker process found — RAM already free")
            result["ram_released"] = True
            return result

        deadline = asyncio.get_event_loop().time() + wait_s
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(POLL_INTERVAL_S)
            rss_mb = await asyncio.to_thread(self._get_pid_rss_mb, worker_pid)
            logger.debug("force_unload_all: llmworker pid=%d rss=%.0f MB", worker_pid, rss_mb)
            if rss_mb < RAM_FREE_THRESHOLD_MB:
                result["ram_released"] = True
                logger.info(
                    "force_unload_all: llmworker RAM released (rss=%.0f MB < %d MB)",
                    rss_mb, RAM_FREE_THRESHOLD_MB,
                )
                return result

        # Step 4 — timeout: optionally SIGKILL
        if kill_on_timeout:
            try:
                import os
                os.kill(worker_pid, signal.SIGKILL)
                result["killed"] = True
                logger.warning(
                    "force_unload_all: SIGKILL sent to llmworker pid=%d after %.0fs timeout",
                    worker_pid, wait_s,
                )
                await asyncio.sleep(2.0)  # let OS reclaim pages
                result["ram_released"] = True
            except ProcessLookupError:
                result["ram_released"] = True  # already gone
            except Exception as exc:
                logger.error("force_unload_all: SIGKILL failed for pid=%d: %s", worker_pid, exc)
        else:
            logger.warning(
                "force_unload_all: llmworker pid=%d still holding RAM after %.0fs",
                worker_pid, wait_s,
            )

        return result

    @staticmethod
    def _find_llmworker_pid() -> Optional[int]:
        """Return the PID of the LM Studio llmworker subprocess, or None.

        Searches for any process whose command args include 'llmworker.js'.
        Runs in a thread (uses subprocess).
        """
        try:
            out = subprocess.check_output(
                ["pgrep", "-f", "llmworker.js"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            pids = [int(p) for p in out.splitlines() if p.strip().isdigit()]
            return pids[0] if pids else None
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            return None

    @staticmethod
    def _get_pid_rss_mb(pid: int) -> float:
        """Return the RSS (resident set size) of a PID in MB, or a large number if gone.

        Runs in a thread (uses subprocess ps).
        """
        try:
            out = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "rss="],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            # macOS ps returns RSS in KB
            return int(out) / 1024.0 if out else 0.0
        except (subprocess.CalledProcessError, ValueError):
            return 0.0  # process gone

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
