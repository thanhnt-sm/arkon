"""
LM Studio REST fallback client — implements the same surface as LMSClient
without requiring the `lmstudio` SDK package.

All LM Studio REST paths:
  GET  /api/v0/models                  list loaded models (also used for health)
  POST /api/v0/models/load             load a model
  POST /api/v0/models/unload           unload a model
  POST /v1/chat/completions            OpenAI-compat chat (predict)

Auth: ``Authorization: Bearer {token}`` if a non-empty token is provided.
Zero side-effects at construction time — no network calls until a method is invoked.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from app.ai.local_orchestrator.lms_client import LoadOptions, SamplingParams

logger = logging.getLogger(__name__)

# REST endpoint paths
_PATH_MODELS = "/api/v0/models"
_PATH_LOAD = "/api/v0/models/load"
_PATH_UNLOAD = "/api/v0/models/unload"
_PATH_CHAT = "/v1/chat/completions"  # OpenAI-compat for predict

# How long to wait for the list/health check endpoint (lightweight)
_HEALTH_TIMEOUT_S = 5.0


class LMSRestClient:
    """
    httpx-based REST client implementing the same async interface as LMSClient.

    Designed to be a transparent fallback when the ``lmstudio`` Python SDK is
    not installed. Accepts identical parameters so callers need no branching.
    """

    def __init__(
        self,
        host: str,
        auth_token: str = "",
        default_timeout_s: float = 120.0,
    ) -> None:
        self._base_url = host.rstrip("/")
        # Auth token must never appear in logs; store raw for header construction only
        self._auth_token = auth_token
        self._default_timeout_s = default_timeout_s

        # Inflight counter — keyed by instance_id; mutated under _lock
        self._inflight: dict[str, int] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build request headers; include Authorization only when token set."""
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth_token:
            h["Authorization"] = f"Bearer {self._auth_token}"
        return h

    def _timeout(self, override: Optional[float]) -> float:
        return override if override is not None else self._default_timeout_s

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def load(
        self,
        model_id: str,
        load_options: "LoadOptions",
        timeout_s: Optional[float] = None,
    ) -> str:
        """
        Load a model via POST /api/v0/models/load.

        Returns the ``instance_id`` string from the response.
        Raises ``httpx.HTTPStatusError`` on 4xx/5xx; ``TimeoutError`` on timeout.
        """
        payload: dict = {
            "model": model_id,
            "context_length": load_options.context_length,
            "eval_batch_size": load_options.eval_batch_size,
            "flash_attention": load_options.flash_attention,
            "offload_kv_cache_to_gpu": load_options.kv_cache_gpu_offload,
        }
        if load_options.ttl_seconds is not None:
            payload["ttl"] = load_options.ttl_seconds

        # gpu.ratio has no direct REST equivalent at /api/v0; pass as hint if possible
        # NOTE: the REST API does not expose a gpu ratio field at this endpoint.
        # gpu_ratio is silently ignored here — use SDK mode for full options.

        logger.debug("REST load: model=%s", model_id)
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=self._timeout(timeout_s),
        ) as client:
            resp = await client.post(self._url(_PATH_LOAD), json=payload)
            resp.raise_for_status()
            data = resp.json()

        instance_id: str = data.get("instance_id", model_id)
        logger.info("REST load complete: instance_id=%s", instance_id)
        return instance_id

    async def unload(self, instance_id: str) -> None:
        """
        Unload a model via POST /api/v0/models/unload.

        Callers MUST check inflight before calling — this method does NOT
        enforce the BusyError guard (that lives in LMSClient).
        """
        logger.debug("REST unload: instance_id=%s", instance_id)
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=self._default_timeout_s,
        ) as client:
            resp = await client.post(
                self._url(_PATH_UNLOAD),
                json={"instance_id": instance_id},
            )
            resp.raise_for_status()
        logger.info("REST unload complete: instance_id=%s", instance_id)

    async def list_loaded(self) -> list[str]:
        """Return list of currently loaded model instance_ids."""
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=_HEALTH_TIMEOUT_S,
        ) as client:
            resp = await client.get(self._url(_PATH_MODELS))
            resp.raise_for_status()
            data = resp.json()

        # Response shape: {"data": [{"id": "...", "type": "llm", ...}, ...]}
        models = data.get("data", data if isinstance(data, list) else [])
        return [m.get("id", "") for m in models if m.get("id")]

    async def health(self) -> bool:
        """Ping GET /api/v0/models — returns True if reachable and 2xx."""
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                timeout=_HEALTH_TIMEOUT_S,
            ) as client:
                resp = await client.get(self._url(_PATH_MODELS))
                return resp.status_code < 400
        except Exception as exc:  # network errors are unhealthy, not fatal
            logger.debug("REST health check failed: %s", exc)
            return False

    async def predict(
        self,
        instance_id: str,
        messages: list[dict],
        sampling: "SamplingParams",
        timeout_s: Optional[float] = None,
    ) -> str:
        """
        Run inference via POST /v1/chat/completions (OpenAI-compat).

        Inflight tracking is NOT duplicated here — LMSClient manages it.
        Returns the assistant message content string.
        """
        payload: dict = {
            "model": instance_id,
            "messages": messages,
        }
        # Inject non-None sampling params into the request body
        if sampling.temperature is not None:
            payload["temperature"] = sampling.temperature
        if sampling.top_p is not None:
            payload["top_p"] = sampling.top_p
        if sampling.top_k is not None:
            # Not OpenAI-standard but LM Studio honours it
            payload["top_k"] = sampling.top_k
        if sampling.min_p is not None:
            payload["min_p"] = sampling.min_p
        if sampling.repeat_penalty is not None:
            payload["repeat_penalty"] = sampling.repeat_penalty
        if sampling.max_tokens is not None:
            payload["max_tokens"] = sampling.max_tokens
        if sampling.seed is not None:
            payload["seed"] = sampling.seed

        logger.debug("REST predict: instance_id=%s", instance_id)
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=self._timeout(timeout_s),
        ) as client:
            resp = await client.post(self._url(_PATH_CHAT), json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Standard OpenAI response: choices[0].message.content
        try:
            content: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Unexpected LM Studio response format: {data!r}") from exc

        return content
