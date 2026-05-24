"""
Unit tests for app/ai/local_orchestrator/provider_adapter.py

All tests use AsyncMock for PhaseRouter — no LM Studio connection, no DB.

Test coverage:
  1. LocalOrchestratorLLM.generate routes "EXTRACT" system → map_extract
  2. LocalOrchestratorLLM.generate routes "DIGEST" system → digest_summary
  3. LocalOrchestratorLLM.generate defaults to refine_write
  4. LocalOrchestratorLLM.generate explicit phase override via config.extra
  5. LocalOrchestratorVision.analyze_image → router.run_phase("vision_caption", ...)
  6. LocalOrchestratorEmbedding.embed → router.embed([text], task="search_query")[0]
  7. LocalOrchestratorEmbedding.embed_batch → router.embed(texts, task="document")
  8. test_connection success path (LLM)
  9. test_connection success path (Vision)
  10. test_connection success path (Embedding)
  11. LocalOrchestratorEmbedding.dimensions falls back to config.dimensions
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.ai.providers.base import ProviderConfig, ProviderType
from app.ai.local_orchestrator.provider_adapter import (
    LocalOrchestratorEmbedding,
    LocalOrchestratorLLM,
    LocalOrchestratorVision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_router_mock() -> AsyncMock:
    """Build a minimal PhaseRouter mock."""
    router = AsyncMock()
    router.run_phase = AsyncMock(return_value="router response")
    router.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    # _lms.health for test_connection
    router._lms = AsyncMock()
    router._lms.health = AsyncMock(return_value=True)
    # _embedding.health for embedding test_connection
    router._embedding = AsyncMock()
    router._embedding.health = AsyncMock(return_value=True)
    router._embedding.dimensions = 1536
    return router


def _llm_provider_config(extra: dict | None = None) -> ProviderConfig:
    return ProviderConfig(
        provider=ProviderType.OPENAI,
        model_id="main-llm-model",
        base_url="http://localhost:1234",
        extra=extra or {},
    )


def _vision_provider_config() -> ProviderConfig:
    return ProviderConfig(
        provider=ProviderType.OPENAI,
        model_id="vision-model",
        base_url="http://localhost:1234",
    )


def _embedding_provider_config(dimensions: int | None = None) -> ProviderConfig:
    return ProviderConfig(
        provider=ProviderType.OPENAI,
        model_id="embed-model",
        base_url="http://localhost:1234",
        dimensions=dimensions,
    )


# ---------------------------------------------------------------------------
# LocalOrchestratorLLM tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_generate_extract_keyword_routes_map_extract():
    router = _make_router_mock()
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    result = await llm.generate("chunk text", system="EXTRACT JSON from this")

    assert result == "router response"
    router.run_phase.assert_called_once()
    call_args = router.run_phase.call_args
    assert call_args[0][0] == "map_extract"
    messages = call_args[1]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "chunk text"


@pytest.mark.asyncio
async def test_llm_generate_json_keyword_routes_map_extract():
    router = _make_router_mock()
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    await llm.generate("some prompt", system="Output strict JSON")

    call_args = router.run_phase.call_args
    assert call_args[0][0] == "map_extract"


@pytest.mark.asyncio
async def test_llm_generate_digest_keyword_routes_digest_summary():
    router = _make_router_mock()
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    await llm.generate("content", system="DIGEST this article")

    call_args = router.run_phase.call_args
    assert call_args[0][0] == "digest_summary"


@pytest.mark.asyncio
async def test_llm_generate_no_system_defaults_refine_write():
    router = _make_router_mock()
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    await llm.generate("write a wiki section")

    call_args = router.run_phase.call_args
    assert call_args[0][0] == "refine_write"


@pytest.mark.asyncio
async def test_llm_generate_explicit_phase_override():
    router = _make_router_mock()
    llm = LocalOrchestratorLLM(
        _llm_provider_config(extra={"phase": "reduce_plan"}), router
    )

    # Even with "EXTRACT" keyword, explicit override wins
    await llm.generate("prompt", system="EXTRACT something")

    call_args = router.run_phase.call_args
    assert call_args[0][0] == "reduce_plan"


@pytest.mark.asyncio
async def test_llm_generate_no_system_no_messages_without_system_key():
    """When system is None, messages list must NOT contain a system turn."""
    router = _make_router_mock()
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    await llm.generate("user prompt only")

    messages = router.run_phase.call_args[1]["messages"]
    roles = [m["role"] for m in messages]
    assert "system" not in roles
    assert roles == ["user"]


@pytest.mark.asyncio
async def test_llm_test_connection_success():
    router = _make_router_mock()
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    ok, msg = await llm.test_connection()

    assert ok is True
    assert "reachable" in msg.lower()


@pytest.mark.asyncio
async def test_llm_test_connection_failure():
    router = _make_router_mock()
    router._lms.health = AsyncMock(return_value=False)
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    ok, msg = await llm.test_connection()

    assert ok is False


@pytest.mark.asyncio
async def test_llm_test_connection_exception():
    router = _make_router_mock()
    router._lms.health = AsyncMock(side_effect=ConnectionError("refused"))
    llm = LocalOrchestratorLLM(_llm_provider_config(), router)

    ok, msg = await llm.test_connection()

    assert ok is False
    assert "unreachable" in msg.lower()


# ---------------------------------------------------------------------------
# LocalOrchestratorVision tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_analyze_image_calls_vision_caption_phase():
    router = _make_router_mock()
    router.run_phase = AsyncMock(return_value="Hình ảnh sơ đồ kiến trúc...")
    vision = LocalOrchestratorVision(_vision_provider_config(), router)

    result = await vision.analyze_image(
        b"\xff\xd8\xff\xe0",
        mime_type="image/jpeg",
        prompt="Page about networking",
    )

    assert result == "Hình ảnh sơ đồ kiến trúc..."
    router.run_phase.assert_called_once_with(
        "vision_caption",
        image_bytes=b"\xff\xd8\xff\xe0",
        mime_type="image/jpeg",
        prompt="Page about networking",
    )


@pytest.mark.asyncio
async def test_vision_analyze_image_default_mime_type():
    router = _make_router_mock()
    vision = LocalOrchestratorVision(_vision_provider_config(), router)

    await vision.analyze_image(b"data")

    call_kwargs = router.run_phase.call_args[1]
    assert call_kwargs["mime_type"] == "image/jpeg"
    assert call_kwargs["prompt"] is None


@pytest.mark.asyncio
async def test_vision_test_connection_success():
    router = _make_router_mock()
    vision = LocalOrchestratorVision(_vision_provider_config(), router)

    ok, msg = await vision.test_connection()

    assert ok is True


@pytest.mark.asyncio
async def test_vision_test_connection_failure():
    router = _make_router_mock()
    router._lms.health = AsyncMock(return_value=False)
    vision = LocalOrchestratorVision(_vision_provider_config(), router)

    ok, msg = await vision.test_connection()

    assert ok is False


# ---------------------------------------------------------------------------
# LocalOrchestratorEmbedding tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embedding_embed_single_uses_search_query_task():
    router = _make_router_mock()
    router.embed = AsyncMock(return_value=[[0.5, 0.6, 0.7]])
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(), router)

    result = await emb.embed("what is TCP/IP?")

    router.embed.assert_called_once_with(["what is TCP/IP?"], task="search_query")
    assert result == [0.5, 0.6, 0.7]


@pytest.mark.asyncio
async def test_embedding_embed_batch_uses_document_task():
    router = _make_router_mock()
    router.embed = AsyncMock(return_value=[[0.1], [0.2], [0.3]])
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(), router)

    texts = ["doc one", "doc two", "doc three"]
    result = await emb.embed_batch(texts)

    router.embed.assert_called_once_with(texts, task="document")
    assert result == [[0.1], [0.2], [0.3]]


@pytest.mark.asyncio
async def test_embedding_embed_batch_concurrency_param_accepted():
    """concurrency parameter accepted for interface compat (not used internally)."""
    router = _make_router_mock()
    router.embed = AsyncMock(return_value=[[0.0]])
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(), router)

    # Should not raise
    await emb.embed_batch(["text"], concurrency=10)
    router.embed.assert_called_once()


@pytest.mark.asyncio
async def test_embedding_test_connection_success():
    router = _make_router_mock()
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(), router)

    ok, msg = await emb.test_connection()

    assert ok is True
    assert "healthy" in msg.lower()


@pytest.mark.asyncio
async def test_embedding_test_connection_failure():
    router = _make_router_mock()
    router._embedding.health = AsyncMock(return_value=False)
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(), router)

    ok, msg = await emb.test_connection()

    assert ok is False


def test_embedding_dimensions_from_embedding_service():
    """dimensions property reads from EmbeddingService when loaded."""
    router = _make_router_mock()
    router._embedding.dimensions = 1536
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(dimensions=512), router)

    # EmbeddingService dimension takes priority
    assert emb.dimensions == 1536


def test_embedding_dimensions_fallback_to_config():
    """dimensions falls back to config.dimensions when service not yet loaded."""
    router = _make_router_mock()
    router._embedding.dimensions = None  # not yet loaded
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(dimensions=768), router)

    assert emb.dimensions == 768


def test_embedding_dimensions_ultimate_fallback():
    """dimensions falls back to 1536 when both service and config are unset."""
    router = _make_router_mock()
    router._embedding.dimensions = None
    emb = LocalOrchestratorEmbedding(_embedding_provider_config(dimensions=None), router)

    assert emb.dimensions == 1536
