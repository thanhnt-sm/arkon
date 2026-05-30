"""
Unit tests for app/ai/local_orchestrator/phase_router.py

All tests are pure — no LM Studio connection, no DB.
LMSClient and EmbeddingService are replaced with AsyncMock / MagicMock.

Test coverage (≥8 cases):
  1.  Initial state is IDLE
  2.  ensure_loaded("vision_caption") from IDLE → VISION_ACTIVE, 1 load, 0 unload
  3.  ensure_loaded("map_extract") after vision active → 1 unload + 1 load → MAIN_LLM_ACTIVE
  4.  Same-slot repeat call → no extra load/unload (idempotent)
  5.  run_phase("vision_caption", image_bytes=b"...") returns predict result
  6.  shutdown() unloads current, state → IDLE
  7.  Mode "max" → LoadOptions carries gpu_ratio + flash_attention + eval_batch_size
  8.  Mode "other" → LoadOptions has only context_length (no gpu_ratio etc.)
  9.  Concurrent ensure_loaded calls serialized by lock — exactly 1 load total
  10. run_phase("map_extract", messages=[...]) delegates to lms.predict
  11. embed() routes to EmbeddingService, never calls lms.predict
  12. Unknown phase raises ValueError
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.local_orchestrator.config import (
    EmbeddingConfig,
    MainLLMConfig,
    VisionConfig,
    LocalAIConfig,
)
from app.ai.local_orchestrator.lms_client import LoadOptions, SamplingParams
from app.ai.local_orchestrator.phase_router import (
    PhaseRouter,
    RouterState,
    PHASE_TO_SLOT,
    get_router,
    reset_router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(mode: str = "max") -> LocalAIConfig:
    """Build a LocalAIConfig without hitting the DB."""
    return LocalAIConfig(
        mode=mode,
        lms_host="http://localhost:1234",
        lms_auth_token="",
        vision=VisionConfig(
            model_id="vision-model",
            fallback_model_id="vision-fallback",
            context_length=8192,
            eval_batch_size=16,
            gpu_ratio=1.0,
        ),
        main_llm=MainLLMConfig(
            model_id="main-llm-model",
            fallback_model_id="main-llm-fallback",
            context_length=32768,
            eval_batch_size=256,
            gpu_ratio=1.0,
            flash_attention=True,
            kv_cache_offload=True,
        ),
        embedding=EmbeddingConfig(
            model_id="embed-model",
            fallback_model_id="embed-fallback",
        ),
    )


def _make_lms_mock(instance_id: str = "inst-abc") -> AsyncMock:
    """Build an AsyncMock satisfying LMSClientProtocol."""
    mock = AsyncMock()
    mock.load = AsyncMock(return_value=instance_id)
    mock.unload = AsyncMock(return_value=None)
    mock.predict = AsyncMock(return_value="mock response")
    mock.health = AsyncMock(return_value=True)
    mock.list_loaded = AsyncMock(return_value=[instance_id])
    return mock


def _make_embedding_mock() -> AsyncMock:
    """Build an AsyncMock for EmbeddingService."""
    mock = AsyncMock()
    mock.embed_document = AsyncMock(return_value=[[0.1, 0.2]])
    mock.embed_query = AsyncMock(return_value=[0.3, 0.4])
    mock.health = AsyncMock(return_value=True)
    mock.dimensions = 1536
    return mock


def _make_router(mode: str = "max", instance_id: str = "inst-abc") -> tuple:
    """Return (router, lms_mock, emb_mock) for test use."""
    config = _make_config(mode)
    lms = _make_lms_mock(instance_id)
    emb = _make_embedding_mock()
    router = PhaseRouter(lms_client=lms, embedding_service=emb, config=config)
    return router, lms, emb


# ---------------------------------------------------------------------------
# Test 1: Initial state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_state_is_idle():
    router, _, _ = _make_router()
    assert router.state == RouterState.IDLE
    assert router._current_slot is None
    assert router._current_instance_id is None


# ---------------------------------------------------------------------------
# Test 2: ensure_loaded vision from IDLE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_loaded_vision_from_idle():
    router, lms, _ = _make_router()

    instance_id = await router.ensure_loaded("vision_caption")

    assert instance_id == "inst-abc"
    assert router.state == RouterState.VISION_ACTIVE
    assert router._current_slot == "vision"
    assert router._current_instance_id == "inst-abc"
    lms.load.assert_called_once()
    lms.unload.assert_not_called()
    # Verify model_id passed to load
    call_args = lms.load.call_args
    assert call_args[0][0] == "vision-model"


# ---------------------------------------------------------------------------
# Test 3: Swap from vision to main_llm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swap_vision_to_main_llm():
    router, lms, _ = _make_router()

    # First load vision
    await router.ensure_loaded("vision_caption")
    lms.load.reset_mock()
    lms.unload.reset_mock()

    # Then load main_llm — must unload vision first
    instance_id = await router.ensure_loaded("map_extract")

    assert instance_id == "inst-abc"
    assert router.state == RouterState.MAIN_LLM_ACTIVE
    assert router._current_slot == "main_llm"
    lms.unload.assert_called_once_with("inst-abc")
    lms.load.assert_called_once()
    call_args = lms.load.call_args
    assert call_args[0][0] == "main-llm-model"


# ---------------------------------------------------------------------------
# Test 4: Same-phase repeat is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_phase_repeat_no_reload():
    router, lms, _ = _make_router()

    await router.ensure_loaded("map_extract")
    lms.load.reset_mock()
    lms.unload.reset_mock()

    # Second call for same slot → no-op
    await router.ensure_loaded("refine_write")  # same slot: main_llm
    lms.load.assert_not_called()
    lms.unload.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: run_phase vision_caption returns predict result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_phase_vision_caption_returns_predict_result():
    router, lms, _ = _make_router()
    lms.predict = AsyncMock(return_value="Hình ảnh cho thấy...")

    result = await router.run_phase("vision_caption", image_bytes=b"\xff\xd8\xff")
    assert result == "Hình ảnh cho thấy..."
    lms.predict.assert_called_once()
    # instance_id and messages passed correctly
    call_args = lms.predict.call_args
    assert call_args[0][0] == "inst-abc"
    messages = call_args[0][1]
    assert any(m["role"] == "system" for m in messages)


# ---------------------------------------------------------------------------
# Test 6: shutdown() unloads and returns to IDLE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_unloads_and_returns_idle():
    router, lms, _ = _make_router()

    await router.ensure_loaded("map_extract")
    assert router.state == RouterState.MAIN_LLM_ACTIVE

    await router.shutdown()

    assert router.state == RouterState.IDLE
    assert router._current_slot is None
    assert router._current_instance_id is None
    lms.unload.assert_called_once_with("inst-abc")


# ---------------------------------------------------------------------------
# Test 7: MAX mode builds full LoadOptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_mode_full_load_options():
    router, lms, _ = _make_router(mode="max")
    await router.ensure_loaded("map_extract")

    call_args = lms.load.call_args
    load_opts: LoadOptions = call_args[0][1]
    # MAX mode includes gpu_ratio, flash_attention, eval_batch_size
    assert load_opts.gpu_ratio == 1.0
    assert load_opts.flash_attention is True
    assert load_opts.eval_batch_size == 256
    assert load_opts.context_length == 32768


# ---------------------------------------------------------------------------
# Test 8: OTHER mode minimal LoadOptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_other_mode_minimal_load_options():
    router, lms, _ = _make_router(mode="other")
    await router.ensure_loaded("map_extract")

    call_args = lms.load.call_args
    load_opts: LoadOptions = call_args[0][1]
    # OTHER mode: only context_length set; advanced load hints are omitted.
    assert load_opts.context_length == 32768
    assert load_opts.gpu_ratio is None
    assert load_opts.flash_attention is None
    assert load_opts.eval_batch_size is None


# ---------------------------------------------------------------------------
# Test 9: Concurrent ensure_loaded serialized by lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_ensure_loaded_serialized():
    """Two concurrent calls for the same slot must result in exactly 1 load."""
    router, lms, _ = _make_router()

    # Introduce a small delay in load to expose race windows
    async def _slow_load(model_id, load_options):
        await asyncio.sleep(0.01)
        return "inst-abc"

    lms.load = AsyncMock(side_effect=_slow_load)

    results = await asyncio.gather(
        router.ensure_loaded("map_extract"),
        router.ensure_loaded("map_extract"),
    )

    assert results[0] == results[1] == "inst-abc"
    # Exactly one load call — second coroutine hit the idempotent path
    assert lms.load.call_count == 1


# ---------------------------------------------------------------------------
# Test 10: run_phase main_llm with pre-built messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_phase_main_llm_with_messages():
    router, lms, _ = _make_router()
    lms.predict = AsyncMock(return_value="Extracted JSON...")

    messages = [
        {"role": "system", "content": "EXTRACT JSON"},
        {"role": "user", "content": "chunk text here"},
    ]
    result = await router.run_phase("map_extract", messages=messages)

    assert result == "Extracted JSON..."
    lms.predict.assert_called_once()
    call_args = lms.predict.call_args
    assert call_args[0][1] == messages
    assert call_args[0][2].response_format_json is True


# ---------------------------------------------------------------------------
# Test 11: embed() routes to EmbeddingService, never calls lms.predict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_uses_embedding_service_not_lms():
    router, lms, emb = _make_router()

    result = await router.embed(["hello world"], task="document")

    emb.embed_document.assert_called_once_with(["hello world"])
    lms.predict.assert_not_called()
    assert result == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_embed_query_routes_to_embed_query():
    router, lms, emb = _make_router()

    result = await router.embed(["search query"], task="search_query")

    emb.embed_query.assert_called_once_with("search query")
    lms.predict.assert_not_called()
    assert result == [[0.3, 0.4]]


# ---------------------------------------------------------------------------
# Test 12: Unknown phase raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_phase_raises_value_error():
    router, _, _ = _make_router()

    with pytest.raises(ValueError, match="Unknown phase"):
        await router.ensure_loaded("nonexistent_phase")


# ---------------------------------------------------------------------------
# Test 13: shutdown from IDLE is safe (no-op)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_from_idle_is_safe():
    router, lms, _ = _make_router()
    # Should not raise
    await router.shutdown()
    lms.unload.assert_not_called()
    assert router.state == RouterState.IDLE


# ---------------------------------------------------------------------------
# Test 14: PHASE_TO_SLOT mapping sanity
# ---------------------------------------------------------------------------


def test_phase_to_slot_mapping():
    assert PHASE_TO_SLOT["vision_caption"] == "vision"
    for phase in ("map_extract", "reduce_plan", "refine_write", "verify_check", "digest_summary"):
        assert PHASE_TO_SLOT[phase] == "main_llm"


# ---------------------------------------------------------------------------
# Test 15: get_router / reset_router singleton lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_router_reset_router_singleton():
    """reset_router clears singleton; next get_router rebuilds it."""
    await reset_router()  # ensure clean state

    fake_config = _make_config("other")
    fake_lms = _make_lms_mock()
    fake_emb = _make_embedding_mock()
    lms_client_cls = MagicMock(return_value=fake_lms)

    with (
        patch(
            "app.ai.local_orchestrator.phase_router.load_config",
            new=AsyncMock(return_value=fake_config),
        ),
        patch(
            "app.ai.local_orchestrator.phase_router.LMSClientGuarded",
            lms_client_cls,
        ),
        patch(
            "app.ai.local_orchestrator.phase_router.EmbeddingService",
            return_value=fake_emb,
        ),
    ):
        mock_session = MagicMock()
        router1 = await get_router(mock_session)
        router2 = await get_router(mock_session)
        # Same singleton
        assert router1 is router2
        assert lms_client_cls.call_args.kwargs["default_timeout_s"] == 300.0

        await reset_router()

        # After reset, next call rebuilds
        router3 = await get_router(mock_session)
        assert router3 is not router1

    # Cleanup singleton for other tests
    await reset_router()
