"""
Provider adapters — drop-in implementations of LLMProvider, VisionProvider,
and EmbeddingProvider that delegate to PhaseRouter.

These classes are returned by ProviderRegistry when ``local_ai.mode != "off"``.
They expose the same public interface as the OpenAI/Google providers so that
callers (mrp/pipeline.py, worker.py) require zero changes.

Heuristic phase routing in LocalOrchestratorLLM.generate():
  - system contains "JSON" or "EXTRACT" → map_extract
  - system contains "DIGEST"            → digest_summary
  - default                             → refine_write
  Caller can override by setting ``config.extra["phase"]``.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    VisionProvider,
)

# TYPE_CHECKING guard avoids circular import at runtime; PhaseRouter imported
# lazily inside methods where needed for isinstance checks.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.local_orchestrator.phase_router import PhaseRouter


# ---------------------------------------------------------------------------
# LLM adapter
# ---------------------------------------------------------------------------


class LocalOrchestratorLLM(LLMProvider):
    """LLMProvider backed by PhaseRouter.

    Phase is selected heuristically from ``system`` prompt content, or
    explicitly via ``config.extra["phase"]``.
    """

    def __init__(self, config: ProviderConfig, router: "PhaseRouter") -> None:
        super().__init__(config)
        self._router = router

    def _select_phase(self, system: Optional[str]) -> str:
        """Heuristic phase selection from system prompt keywords."""
        # Explicit override takes priority
        explicit: Optional[str] = self.config.extra.get("phase")
        if explicit:
            return explicit

        if system:
            upper = system.upper()
            if "JSON" in upper or "EXTRACT" in upper:
                return "map_extract"
            if "DIGEST" in upper:
                return "digest_summary"
            if "REDUCE" in upper or "PLAN" in upper:
                return "reduce_plan"
            if "VERIFY" in upper or "AUDIT" in upper:
                return "verify_check"

        return "refine_write"

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate text via the PhaseRouter.

        Builds a messages list from ``system`` + ``prompt``, selects the
        appropriate MRP phase, and delegates to router.run_phase().

        Args:
            prompt: User-turn content.
            system: System prompt (used for phase heuristic).
            max_tokens: Unused — sampling is controlled by phase profile.
            temperature: Unused — sampling is controlled by phase profile.

        Returns:
            LLM response string.
        """
        phase = self._select_phase(system)
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        logger.debug(
            "LocalOrchestratorLLM.generate: phase={} messages={}", phase, len(messages)
        )
        return await self._router.run_phase(phase, messages=messages)

    async def test_connection(self) -> tuple[bool, str]:
        """Ping LM Studio health endpoint via the router's LMS client."""
        try:
            # Access internal _lms for health check — acceptable as same package.
            healthy = await self._router._lms.health()
            if healthy:
                return (True, "LM Studio reachable")
            return (False, "LM Studio health check returned False")
        except Exception as exc:
            return (False, f"LM Studio unreachable: {exc}")


# ---------------------------------------------------------------------------
# Vision adapter
# ---------------------------------------------------------------------------


class LocalOrchestratorVision(VisionProvider):
    """VisionProvider backed by PhaseRouter vision_caption phase."""

    def __init__(self, config: ProviderConfig, router: "PhaseRouter") -> None:
        super().__init__(config)
        self._router = router

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
    ) -> str:
        """Analyze an image via the vision_caption phase.

        Args:
            image_data: Raw image bytes.
            mime_type: Image MIME type.
            prompt: Optional context hint for the vision system prompt.

        Returns:
            Vietnamese caption string.
        """
        logger.debug(
            "LocalOrchestratorVision.analyze_image: mime_type={} bytes={}",
            mime_type,
            len(image_data),
        )
        return await self._router.run_phase(
            "vision_caption",
            image_bytes=image_data,
            mime_type=mime_type,
            prompt=prompt,
        )

    async def test_connection(self) -> tuple[bool, str]:
        """Ping LM Studio health endpoint."""
        try:
            healthy = await self._router._lms.health()
            if healthy:
                return (True, "LM Studio reachable")
            return (False, "LM Studio health check returned False")
        except Exception as exc:
            return (False, f"LM Studio unreachable: {exc}")


# ---------------------------------------------------------------------------
# Embedding adapter
# ---------------------------------------------------------------------------


class LocalOrchestratorEmbedding(EmbeddingProvider):
    """EmbeddingProvider backed by in-process EmbeddingService (no LMSClient).

    ``dimensions`` defaults to 1024 (gte-Qwen2-1.5B-instruct output size)
    until the model is loaded and the real dimension is known.
    """

    def __init__(self, config: ProviderConfig, router: "PhaseRouter") -> None:
        super().__init__(config)
        self._router = router

    async def embed(self, text: str) -> list[float]:
        """Embed a single query string.

        Uses "search_query" task prefix for gte-Qwen2 models.
        """
        results = await self._router.embed([text], task="search_query")
        return results[0]

    async def embed_batch(
        self, texts: list[str], concurrency: int = 5
    ) -> list[list[float]]:
        """Embed a batch of document strings.

        Uses "document" task prefix. The ``concurrency`` parameter is accepted
        for interface compatibility but EmbeddingService handles batching
        internally with its own batch_size.
        """
        return await self._router.embed(texts, task="document")

    async def test_connection(self) -> tuple[bool, str]:
        """Check that the in-process embedding model loads successfully."""
        try:
            healthy = await self._router._embedding.health()
            if healthy:
                return (True, "EmbeddingService healthy")
            return (False, "EmbeddingService model failed to load")
        except Exception as exc:
            return (False, f"EmbeddingService error: {exc}")

    @property
    def dimensions(self) -> int:
        """Output vector dimensions.

        Returns the known dimension from EmbeddingService if available,
        otherwise falls back to config or the gte-Qwen2-1.5B default (1536).
        """
        # EmbeddingService only knows dimensions after first encode
        svc_dim = self._router._embedding.dimensions
        if svc_dim is not None:
            return svc_dim
        return self.config.dimensions or 1536
