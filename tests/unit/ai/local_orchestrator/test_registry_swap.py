"""
Unit tests for the local AI registry swap in app/ai/registry.py

Verifies that ProviderRegistry returns LocalOrchestrator* providers when
local_ai.mode != "off", and falls back to the standard OpenAI/Google path
when mode == "off".

All DB and LM Studio calls are mocked — no network, no DB.

Test coverage:
  1. mode="max"   → get_llm() returns LocalOrchestratorLLM
  2. mode="max"   → get_vision() returns LocalOrchestratorVision
  3. mode="max"   → get_embedding() returns LocalOrchestratorEmbedding
  4. mode="other" → get_llm() still returns LocalOrchestratorLLM (not off)
  5. mode="other" → get_vision() still returns LocalOrchestratorVision
  6. mode="other" → get_embedding() still returns LocalOrchestratorEmbedding
  7. mode="off"   → get_llm() falls through to standard path (raises ValueError
                    if no LLM configured — proves LocalOrchestrator NOT returned)
  8. mode="off"   → get_vision() falls through to standard path
  9. mode="off"   → get_embedding() falls through to standard path
  10. _local_ai_active() returns False when load_config raises (defensive)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.local_orchestrator.config import (
    EmbeddingConfig,
    LocalAIConfig,
    MainLLMConfig,
    VisionConfig,
)
from app.ai.local_orchestrator.provider_adapter import (
    LocalOrchestratorEmbedding,
    LocalOrchestratorLLM,
    LocalOrchestratorVision,
)
from app.ai.registry import ProviderRegistry, _local_ai_active


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_local_ai_config(mode: str) -> LocalAIConfig:
    return LocalAIConfig(
        mode=mode,
        lms_host="http://localhost:1234",
        lms_auth_token="",
        vision=VisionConfig(
            model_id="vision-model",
            fallback_model_id="vision-fb",
            context_length=8192,
            eval_batch_size=16,
            gpu_ratio=1.0,
        ),
        main_llm=MainLLMConfig(
            model_id="llm-model",
            fallback_model_id="llm-fb",
            context_length=32768,
            eval_batch_size=256,
            gpu_ratio=1.0,
            flash_attention=True,
            kv_cache_offload=True,
        ),
        embedding=EmbeddingConfig(
            model_id="embed-model",
            fallback_model_id="embed-fb",
        ),
    )


def _make_router_mock() -> AsyncMock:
    router = AsyncMock()
    router._lms = AsyncMock()
    router._embedding = AsyncMock()
    router._embedding.dimensions = 1536
    return router


def _make_db_session() -> MagicMock:
    return MagicMock()


# Patch targets — both registry.py and phase_router.py call load_config
_LOAD_CONFIG_REGISTRY = "app.ai.local_orchestrator.load_config"
_GET_ROUTER_TARGET = "app.ai.local_orchestrator.phase_router.get_router"
# registry imports load_config via `from app.ai.local_orchestrator import load_config`
_LOAD_CONFIG_ORCHESTRATOR = "app.ai.local_orchestrator.load_config"


# ---------------------------------------------------------------------------
# Shared patch context for "local AI active" scenarios
# ---------------------------------------------------------------------------


def _active_patches(mode: str):
    """Return a list of (target, mock) for patching local AI active state."""
    cfg = _make_local_ai_config(mode)
    router = _make_router_mock()
    return cfg, router, [
        patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)),
        patch(_GET_ROUTER_TARGET, new=AsyncMock(return_value=router)),
    ]


# ---------------------------------------------------------------------------
# mode="max" — all three providers swapped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_mode_get_llm_returns_local_orchestrator():
    cfg, router, patches = _active_patches("max")
    db = _make_db_session()

    with patches[0], patches[1]:
        registry = ProviderRegistry(db)
        provider = await registry.get_llm()

    assert isinstance(provider, LocalOrchestratorLLM)
    assert provider.runtime_profile.is_local
    assert provider.runtime_profile.context_length == cfg.main_llm.context_length
    assert provider.runtime_profile.model_name == cfg.main_llm.model_id


@pytest.mark.asyncio
async def test_max_mode_get_vision_returns_local_orchestrator():
    cfg, router, patches = _active_patches("max")
    db = _make_db_session()

    with patches[0], patches[1]:
        registry = ProviderRegistry(db)
        provider = await registry.get_vision()

    assert isinstance(provider, LocalOrchestratorVision)


@pytest.mark.asyncio
async def test_max_mode_get_embedding_returns_local_orchestrator():
    cfg, router, patches = _active_patches("max")
    db = _make_db_session()

    with patches[0], patches[1]:
        registry = ProviderRegistry(db)
        provider = await registry.get_embedding()

    assert isinstance(provider, LocalOrchestratorEmbedding)


# ---------------------------------------------------------------------------
# mode="other" — still returns LocalOrchestrator* (not "off")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_other_mode_get_llm_returns_local_orchestrator():
    cfg, router, patches = _active_patches("other")
    db = _make_db_session()

    with patches[0], patches[1]:
        registry = ProviderRegistry(db)
        provider = await registry.get_llm()

    assert isinstance(provider, LocalOrchestratorLLM)


@pytest.mark.asyncio
async def test_other_mode_get_vision_returns_local_orchestrator():
    cfg, router, patches = _active_patches("other")
    db = _make_db_session()

    with patches[0], patches[1]:
        registry = ProviderRegistry(db)
        provider = await registry.get_vision()

    assert isinstance(provider, LocalOrchestratorVision)


@pytest.mark.asyncio
async def test_other_mode_get_embedding_returns_local_orchestrator():
    cfg, router, patches = _active_patches("other")
    db = _make_db_session()

    with patches[0], patches[1]:
        registry = ProviderRegistry(db)
        provider = await registry.get_embedding()

    assert isinstance(provider, LocalOrchestratorEmbedding)


# ---------------------------------------------------------------------------
# mode="off" — falls through to standard path (no LocalOrchestrator returned)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_off_mode_get_llm_falls_through_to_standard_path():
    """mode=off → get_llm() does NOT return LocalOrchestratorLLM.

    Standard path raises ValueError when no LLM configured in DB — that proves
    the local AI branch was skipped entirely.
    """
    cfg = _make_local_ai_config("off")
    db = _make_db_session()

    with patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)):
        registry = ProviderRegistry(db)
        # Standard path calls _load_llm_config → ConfigService → DB
        # We patch get_active_llm_spec_id to return None (nothing configured)
        with patch.object(registry, "get_active_llm_spec_id", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="No active LLM"):
                await registry.get_llm()


@pytest.mark.asyncio
async def test_off_mode_get_vision_falls_through_to_standard_path():
    """mode=off → get_vision() does NOT return LocalOrchestratorVision.

    Standard path returns None when no vision model configured.
    """
    cfg = _make_local_ai_config("off")
    db = _make_db_session()

    with patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)):
        registry = ProviderRegistry(db)
        with patch.object(
            registry, "get_active_vision_spec_id", new=AsyncMock(return_value=None)
        ):
            result = await registry.get_vision()

    # Standard path: no vision spec → returns None
    assert result is None
    assert not isinstance(result, LocalOrchestratorVision)


@pytest.mark.asyncio
async def test_off_mode_get_embedding_falls_through_to_standard_path():
    """mode=off → get_embedding() does NOT return LocalOrchestratorEmbedding.

    Standard path raises ValueError when no embedding configured.
    """
    cfg = _make_local_ai_config("off")
    db = _make_db_session()

    with patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)):
        registry = ProviderRegistry(db)
        with patch.object(
            registry, "_load_embedding_config", new=AsyncMock(
                side_effect=ValueError("No active embedding model")
            )
        ):
            with pytest.raises(ValueError, match="No active embedding model"):
                await registry.get_embedding()


# ---------------------------------------------------------------------------
# _local_ai_active helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_ai_active_returns_true_for_max():
    cfg = _make_local_ai_config("max")
    with patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)):
        result = await _local_ai_active(MagicMock())
    assert result is True


@pytest.mark.asyncio
async def test_local_ai_active_returns_true_for_other():
    cfg = _make_local_ai_config("other")
    with patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)):
        result = await _local_ai_active(MagicMock())
    assert result is True


@pytest.mark.asyncio
async def test_local_ai_active_returns_false_for_off():
    cfg = _make_local_ai_config("off")
    with patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)):
        result = await _local_ai_active(MagicMock())
    assert result is False


@pytest.mark.asyncio
async def test_local_ai_active_returns_false_on_exception():
    """load_config raising must not propagate — returns False defensively."""
    with patch(
        _LOAD_CONFIG_REGISTRY,
        new=AsyncMock(side_effect=RuntimeError("DB connection lost")),
    ):
        result = await _local_ai_active(MagicMock())
    assert result is False


# ---------------------------------------------------------------------------
# ProviderConfig shape when local AI is active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_mode_llm_provider_config_shape():
    """ProviderConfig passed to LocalOrchestratorLLM reflects LocalAIConfig values."""
    cfg = _make_local_ai_config("max")
    router = _make_router_mock()
    db = _make_db_session()

    with (
        patch(_LOAD_CONFIG_REGISTRY, new=AsyncMock(return_value=cfg)),
        patch(_GET_ROUTER_TARGET, new=AsyncMock(return_value=router)),
    ):
        registry = ProviderRegistry(db)
        provider = await registry.get_llm()

    assert isinstance(provider, LocalOrchestratorLLM)
    assert provider.config.model_id == "llm-model"
    assert provider.config.base_url == "http://localhost:1234"
