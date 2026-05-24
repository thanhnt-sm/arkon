"""
Unit tests for app/ai/local_orchestrator/embedding_service.py

All tests mock sentence_transformers.SentenceTransformer via sys.modules so
the real package need NOT be installed. This keeps CI fast and dependency-free.

Coverage:
- Module import does NOT load sentence-transformers (lazy load)
- Model not instantiated until first embed call (lazy load verified)
- embed_document passes prompt_name="document"
- embed_query passes prompt_name="search_query"
- embed_document returns list[list[float]] of correct shape
- embed_query returns list[float]
- embed_document with empty list returns []
- MPS RuntimeError fallback to CPU
- health() returns True after successful load
- health() returns False when SentenceTransformer raises
- dimensions property is None before first encode, set after
- device property reflects MPS fallback
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch, call
import asyncio

import pytest
import numpy as np

# ---------------------------------------------------------------------------
# Helpers — inject fake sentence_transformers into sys.modules
# ---------------------------------------------------------------------------


def _make_fake_st_module(mock_cls: MagicMock) -> types.ModuleType:
    """Build a minimal fake sentence_transformers module."""
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = mock_cls  # type: ignore[attr-defined]
    return mod


def _make_mock_model(dim: int = 1024, device: str = "mps") -> MagicMock:
    """Return a mock SentenceTransformer instance with a working encode()."""
    model = MagicMock()

    def _encode(texts, prompt_name=None, batch_size=8, convert_to_numpy=True, show_progress_bar=False):
        return np.random.rand(len(texts), dim).astype(np.float32)

    model.encode.side_effect = _encode
    return model


def _inject_st(mock_cls: MagicMock):
    """Inject fake ST module; return original for cleanup."""
    original = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = _make_fake_st_module(mock_cls)
    return original


def _restore_st(original):
    if original is None:
        sys.modules.pop("sentence_transformers", None)
    else:
        sys.modules["sentence_transformers"] = original


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_st_cls():
    """A MagicMock SentenceTransformer class + injected into sys.modules."""
    cls = MagicMock(return_value=_make_mock_model())
    original = _inject_st(cls)
    yield cls
    _restore_st(original)


# ---------------------------------------------------------------------------
# 1. Lazy load — model NOT created on module import or EmbeddingService()
# ---------------------------------------------------------------------------


def test_module_import_does_not_load_sentence_transformers():
    """Importing EmbeddingService must not touch sentence_transformers."""
    tracker = MagicMock()
    original = _inject_st(tracker)
    try:
        # Re-import to force fresh execution path
        import importlib
        import app.ai.local_orchestrator.embedding_service as es_mod
        importlib.reload(es_mod)
        tracker.assert_not_called()
    finally:
        _restore_st(original)


def test_no_model_instantiation_on_construction(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    _ = EmbeddingService("test-model")
    mock_st_cls.assert_not_called()


def test_dimensions_none_before_first_encode(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    assert svc.dimensions is None


# ---------------------------------------------------------------------------
# 2. embed_document — prompt_name="document", correct shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_document_calls_encode_with_document_prompt(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    texts = ["doc one", "doc two"]
    result = await svc.embed_document(texts)

    model_instance = mock_st_cls.return_value
    model_instance.encode.assert_called_once()
    _, kwargs = model_instance.encode.call_args
    assert kwargs.get("prompt_name") == "document"


@pytest.mark.asyncio
async def test_embed_document_returns_list_of_vectors(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    result = await svc.embed_document(["text one", "text two"])

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(v, list) for v in result)
    assert all(isinstance(f, float) for f in result[0])


@pytest.mark.asyncio
async def test_embed_document_empty_list_returns_empty(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    result = await svc.embed_document([])
    assert result == []
    mock_st_cls.assert_not_called()


# ---------------------------------------------------------------------------
# 3. embed_query — prompt_name="search_query", returns single vector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_query_calls_encode_with_search_query_prompt(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    await svc.embed_query("what is transformer?")

    model_instance = mock_st_cls.return_value
    model_instance.encode.assert_called_once()
    _, kwargs = model_instance.encode.call_args
    assert kwargs.get("prompt_name") == "search_query"


@pytest.mark.asyncio
async def test_embed_query_returns_flat_list_of_floats(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    result = await svc.embed_query("query text")

    assert isinstance(result, list)
    assert all(isinstance(f, float) for f in result)


# ---------------------------------------------------------------------------
# 4. Dimensions cached after first encode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dimensions_set_after_first_embed(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    assert svc.dimensions is None
    await svc.embed_query("hello")
    assert svc.dimensions == 1024


# ---------------------------------------------------------------------------
# 5. MPS fallback to CPU on RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mps_runtime_error_falls_back_to_cpu():
    """First SentenceTransformer(device='mps') raises RuntimeError; retry cpu."""
    good_model = _make_mock_model(dim=1024, device="cpu")

    def _side_effect(model_id, device):
        if device == "mps":
            raise RuntimeError("MPS not available")
        return good_model

    mock_cls = MagicMock(side_effect=_side_effect)
    original = _inject_st(mock_cls)
    try:
        from app.ai.local_orchestrator.embedding_service import EmbeddingService
        svc = EmbeddingService("test-model", device="mps")
        result = await svc.embed_query("test")

        assert svc.device == "cpu"
        assert isinstance(result, list)
    finally:
        _restore_st(original)


# ---------------------------------------------------------------------------
# 6. health()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_true_after_successful_load(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    result = await svc.health()
    assert result is True


@pytest.mark.asyncio
async def test_health_returns_false_when_load_raises():
    mock_cls = MagicMock(side_effect=RuntimeError("load failed on both devices"))
    original = _inject_st(mock_cls)
    try:
        from app.ai.local_orchestrator.embedding_service import EmbeddingService
        svc = EmbeddingService("bad-model", device="cpu")
        result = await svc.health()
        assert result is False
    finally:
        _restore_st(original)


# ---------------------------------------------------------------------------
# 7. Properties
# ---------------------------------------------------------------------------


def test_model_id_property(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("Alibaba-NLP/gte-Qwen2-1.5B-instruct")
    assert svc.model_id == "Alibaba-NLP/gte-Qwen2-1.5B-instruct"


def test_device_property_default(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model")
    assert svc.device == "mps"


def test_device_property_override(mock_st_cls):
    from app.ai.local_orchestrator.embedding_service import EmbeddingService
    svc = EmbeddingService("test-model", device="cpu")
    assert svc.device == "cpu"
