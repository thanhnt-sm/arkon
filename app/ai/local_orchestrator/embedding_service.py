"""
In-process embedding service using sentence-transformers on MPS (Apple Metal).

Runs gte-Qwen2-1.5B-instruct locally — bypasses LM Studio because the SDK
does not expose task-prefix control (`prompt_name="document"` vs
`prompt_name="search_query"`).

Design decisions:
- Lazy load: model is NOT imported or instantiated until the first encode call.
- `sentence_transformers` imported INSIDE _ensure_loaded() so the module can
  be imported in environments where ST is not installed (import-time zero cost).
- MPS fallback: RuntimeError on MPS load → warning + retry on CPU.
- Blocking encode() wrapped in asyncio.to_thread for async compatibility.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from loguru import logger

if TYPE_CHECKING:
    # Only for type annotations — never executed at runtime
    from sentence_transformers import SentenceTransformer as _STType


class EmbeddingService:
    """Async wrapper around a sentence-transformers SentenceTransformer model.

    Args:
        model_id: HuggingFace model identifier, e.g.
                  "Alibaba-NLP/gte-Qwen2-1.5B-instruct".
        device:   Torch device string. "mps" for Apple Silicon GPU (default).
                  Falls back to "cpu" automatically on RuntimeError.
        batch_size: Number of texts encoded per forward pass.
    """

    def __init__(
        self,
        model_id: str,
        device: str = "mps",
        batch_size: int = 8,
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._batch_size = batch_size
        self._model: Optional[_STType] = None
        self._dimensions: Optional[int] = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> "_STType":
        """Load the model on first call. Imported lazily to avoid hard dep."""
        if self._model is not None:
            return self._model

        # Deferred import — keeps module loadable without sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for EmbeddingService. "
                "Install with: pip install 'sentence-transformers>=3.0.0'"
            ) from exc

        try:
            logger.debug(
                "EmbeddingService: loading {} on device={}",
                self._model_id,
                self._device,
            )
            self._model = SentenceTransformer(self._model_id, device=self._device)
        except RuntimeError as exc:
            logger.warning(
                "EmbeddingService: failed to load on device={} ({}), "
                "retrying on cpu",
                self._device,
                exc,
            )
            self._device = "cpu"
            self._model = SentenceTransformer(self._model_id, device=self._device)

        return self._model

    def _encode_sync(
        self, texts: list[str], prompt_name: str
    ) -> list[list[float]]:
        """Blocking encode — runs in a thread pool via asyncio.to_thread."""
        model = self._ensure_loaded()
        embeddings = model.encode(
            texts,
            prompt_name=prompt_name,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        # Cache dimension on first successful encode
        if self._dimensions is None and len(embeddings) > 0:
            self._dimensions = int(embeddings[0].shape[0])
        return [vec.tolist() for vec in embeddings]

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def embed_document(self, texts: list[str]) -> list[list[float]]:
        """Encode a list of documents for indexing.

        Uses prompt_name="document" (gte-Qwen2 task prefix for passages).

        Args:
            texts: List of document strings to encode.

        Returns:
            List of float vectors, one per input text.
        """
        if not texts:
            return []
        return await asyncio.to_thread(self._encode_sync, texts, "document")

    async def embed_query(self, text: str) -> list[float]:
        """Encode a single search query.

        Uses prompt_name="search_query" (gte-Qwen2 task prefix for queries).

        Args:
            text: Query string to encode.

        Returns:
            Float vector for the query.
        """
        results = await asyncio.to_thread(self._encode_sync, [text], "search_query")
        return results[0]

    async def health(self) -> bool:
        """Return True if the model loads successfully, False otherwise."""
        try:
            await asyncio.to_thread(self._ensure_loaded)
            return True
        except Exception as exc:
            logger.warning("EmbeddingService.health() failed: {}", exc)
            return False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def dimensions(self) -> Optional[int]:
        """Output vector dimension, or None if model not yet loaded."""
        return self._dimensions

    @property
    def model_id(self) -> str:
        """HuggingFace model identifier as supplied at construction."""
        return self._model_id

    @property
    def device(self) -> str:
        """Active torch device (may differ from constructor arg after MPS fallback)."""
        return self._device
