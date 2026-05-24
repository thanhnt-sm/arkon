"""
Unit tests for app/ai/local_orchestrator/config.py

All tests are pure — no real DB connection.  ConfigService is imported lazily
inside load_config / save_config bodies, so we stub it via sys.modules before
the functions execute.  The orchestrator schemas (Pydantic) and pure helpers
(_config_to_kv, _kv_to_config, is_max_mode) are imported directly without any
DB dependency.

Coverage targets:
  - load returns schema defaults when KV is empty
  - save → load round-trip preserves every field
  - mode validator rejects invalid values
  - partial KV override leaves unset fields at defaults
  - module-level import does NOT call ConfigService (zero side-effects)
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.local_orchestrator.config import (
    LocalAIConfig,
    _config_to_kv,
    _kv_to_config,
    is_max_mode,
    load_config,
    save_config,
)
from app.ai.local_orchestrator.presets import (
    MAX_PRESET,
    MODE_MAX,
    MODE_OFF,
    MODE_OTHER,
    VALID_MODES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session() -> MagicMock:
    """Return a MagicMock that satisfies AsyncSession typing."""
    return MagicMock()


def _make_config_service_get(kv: dict) -> AsyncMock:
    """Return an AsyncMock for ConfigService.get that reads from a dict."""
    async def _get(key: str):
        return kv.get(key)
    return AsyncMock(side_effect=_get)


def _make_config_service_set(store: dict) -> AsyncMock:
    """Return an AsyncMock for ConfigService.set that writes into a dict."""
    async def _set(key: str, value: str):
        store[key] = value
    return AsyncMock(side_effect=_set)


def _inject_config_service_mock(get_fn=None, set_fn=None):
    """
    Inject a fake ConfigService into sys.modules so that the deferred import
    inside load_config / save_config picks up the mock instead of the real
    module (which requires DB + cryptography deps unavailable in unit tests).

    Returns the mock instance that will be returned by ConfigService(session).
    """
    mock_instance = MagicMock()
    if get_fn:
        mock_instance.get = get_fn
    if set_fn:
        mock_instance.set = set_fn

    mock_cls = MagicMock(return_value=mock_instance)

    # Build a minimal fake module hierarchy
    fake_services = types.ModuleType("app.services")
    fake_cs_module = types.ModuleType("app.services.config_service")
    fake_cs_module.ConfigService = mock_cls

    # Preserve whatever is already loaded (app, app.services) but override
    # config_service so the `from app.services.config_service import …` inside
    # load_config / save_config resolves to our fake.
    original_cs = sys.modules.get("app.services.config_service")
    sys.modules["app.services.config_service"] = fake_cs_module

    return mock_instance, mock_cls, original_cs


def _restore_config_service(original_cs):
    if original_cs is None:
        sys.modules.pop("app.services.config_service", None)
    else:
        sys.modules["app.services.config_service"] = original_cs


# ---------------------------------------------------------------------------
# 1. Defaults when KV is empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_returns_defaults_when_kv_empty():
    """All keys missing → config equals schema defaults."""
    session = _mock_session()
    instance, _, original_cs = _inject_config_service_mock(
        get_fn=_make_config_service_get({})
    )
    try:
        config = await load_config(session)
    finally:
        _restore_config_service(original_cs)

    assert config.mode == MODE_OFF
    assert config.lms_host == MAX_PRESET["lms_host"]
    assert config.lms_auth_token == MAX_PRESET["lms_auth_token"]
    assert config.vision.model_id == MAX_PRESET["vision"]["model_id"]
    assert config.vision.fallback_model_id == MAX_PRESET["vision"]["fallback_model_id"]
    assert config.vision.context_length == MAX_PRESET["vision"]["context_length"]
    assert config.main_llm.model_id == MAX_PRESET["main_llm"]["model_id"]
    assert config.main_llm.context_length == MAX_PRESET["main_llm"]["context_length"]
    assert config.main_llm.flash_attention == MAX_PRESET["main_llm"]["flash_attention"]
    assert config.embedding.model_id == MAX_PRESET["embedding"]["model_id"]
    assert config.sampling.refine.temperature == MAX_PRESET["sampling"]["refine"]["temperature"]
    assert config.sampling.map.temperature == MAX_PRESET["sampling"]["map"]["temperature"]
    assert config.sampling.vision.temperature == MAX_PRESET["sampling"]["vision"]["temperature"]


# ---------------------------------------------------------------------------
# 2. Round-trip: save → load preserves values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_load_round_trip():
    """Saving a modified config and loading it back returns identical values."""
    session = _mock_session()
    kv_store: dict = {}

    from app.ai.local_orchestrator.config import VisionConfig, MainLLMConfig

    original = LocalAIConfig(
        mode=MODE_MAX,
        lms_host="http://192.168.1.50:1234",
        lms_auth_token="secret-token",
        vision=VisionConfig(model_id="custom/vision-model", context_length=4096),
        main_llm=MainLLMConfig(context_length=16384, flash_attention=False),
    )

    save_instance, _, original_cs = _inject_config_service_mock(
        set_fn=_make_config_service_set(kv_store)
    )
    try:
        await save_config(session, original)
    finally:
        _restore_config_service(original_cs)

    load_instance, _, original_cs = _inject_config_service_mock(
        get_fn=_make_config_service_get(kv_store)
    )
    try:
        loaded = await load_config(session)
    finally:
        _restore_config_service(original_cs)

    assert loaded.mode == MODE_MAX
    assert loaded.lms_host == "http://192.168.1.50:1234"
    assert loaded.lms_auth_token == "secret-token"
    assert loaded.vision.model_id == "custom/vision-model"
    assert loaded.vision.context_length == 4096
    assert loaded.main_llm.context_length == 16384
    assert loaded.main_llm.flash_attention is False


# ---------------------------------------------------------------------------
# 3. Mode validator rejects invalid values
# ---------------------------------------------------------------------------


def test_mode_validation_rejects_unknown_value():
    """Pydantic must raise ValueError for unrecognised mode strings."""
    with pytest.raises(Exception):  # ValidationError subclasses ValueError
        LocalAIConfig(mode="turbo")


def test_mode_validation_rejects_empty_string():
    with pytest.raises(Exception):
        LocalAIConfig(mode="")


def test_mode_validation_accepts_all_valid_modes():
    for mode in VALID_MODES:
        cfg = LocalAIConfig(mode=mode)
        assert cfg.mode == mode


# ---------------------------------------------------------------------------
# 4. Partial KV override — unset keys fall back to defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_kv_override_leaves_defaults():
    """Only overriding mode and lms_host — all other fields stay at defaults."""
    session = _mock_session()
    partial_kv = {
        "local_ai.mode": MODE_OTHER,
        "local_ai.lms_host": "http://10.0.0.5:1234",
    }

    instance, _, original_cs = _inject_config_service_mock(
        get_fn=_make_config_service_get(partial_kv)
    )
    try:
        config = await load_config(session)
    finally:
        _restore_config_service(original_cs)

    assert config.mode == MODE_OTHER
    assert config.lms_host == "http://10.0.0.5:1234"
    # Unset keys must still equal MAX_PRESET defaults
    assert config.vision.model_id == MAX_PRESET["vision"]["model_id"]
    assert config.main_llm.context_length == MAX_PRESET["main_llm"]["context_length"]
    assert config.embedding.model_id == MAX_PRESET["embedding"]["model_id"]
    assert config.sampling.refine.temperature == MAX_PRESET["sampling"]["refine"]["temperature"]


# ---------------------------------------------------------------------------
# 5. Module import does NOT call ConfigService
# ---------------------------------------------------------------------------


def test_module_import_does_not_call_db():
    """
    ConfigService is only imported inside async function bodies, so accessing
    module-level names (LocalAIConfig, is_max_mode, load_config, save_config)
    must never instantiate ConfigService or touch the DB.

    Strategy: inject a tracking mock into sys.modules and verify it was never
    called after accessing every exported name from the orchestrator package.
    """
    mock_cls = MagicMock()
    fake_cs_module = types.ModuleType("app.services.config_service")
    fake_cs_module.ConfigService = mock_cls
    original_cs = sys.modules.get("app.services.config_service")
    sys.modules["app.services.config_service"] = fake_cs_module

    try:
        from app.ai.local_orchestrator import config as cfg_module

        # Accessing module-level names must not instantiate ConfigService
        _ = cfg_module.LocalAIConfig()
        _ = cfg_module.is_max_mode(cfg_module.LocalAIConfig())
        _ = cfg_module.load_config   # reference only, not a call
        _ = cfg_module.save_config

        mock_cls.assert_not_called()
    finally:
        _restore_config_service(original_cs)


# ---------------------------------------------------------------------------
# 6. is_max_mode helper
# ---------------------------------------------------------------------------


def test_is_max_mode_true_for_max():
    assert is_max_mode(LocalAIConfig(mode=MODE_MAX)) is True


def test_is_max_mode_false_for_off():
    assert is_max_mode(LocalAIConfig(mode=MODE_OFF)) is False


def test_is_max_mode_false_for_other():
    assert is_max_mode(LocalAIConfig(mode=MODE_OTHER)) is False


# ---------------------------------------------------------------------------
# 7. _config_to_kv / _kv_to_config symmetry (pure-function)
# ---------------------------------------------------------------------------


def test_flatten_roundtrip_is_lossless():
    """Flatten to KV then reassemble — result equals original config."""
    original = LocalAIConfig(
        mode=MODE_MAX,
        lms_host="http://host.docker.internal:9999",
        lms_auth_token="tok",
    )
    kv = _config_to_kv(original)
    restored = _kv_to_config(kv)

    assert restored.mode == original.mode
    assert restored.lms_host == original.lms_host
    assert restored.lms_auth_token == original.lms_auth_token
    assert restored.vision.model_id == original.vision.model_id
    assert restored.main_llm.context_length == original.main_llm.context_length
    assert restored.sampling.refine.temperature == original.sampling.refine.temperature
    assert restored.sampling.refine.repeat_penalty == original.sampling.refine.repeat_penalty
    assert restored.sampling.vision.top_k == original.sampling.vision.top_k


def test_flatten_produces_local_ai_prefix_on_all_keys():
    """Every key in the flattened dict must start with `local_ai.`."""
    kv = _config_to_kv(LocalAIConfig())
    assert all(k.startswith("local_ai.") for k in kv), (
        "Found keys without local_ai. prefix: "
        + str([k for k in kv if not k.startswith("local_ai.")])
    )


def test_flatten_key_count_above_minimum():
    """Sanity: seed migration requires 20+ keys; flatten must produce at least that."""
    kv = _config_to_kv(LocalAIConfig())
    assert len(kv) >= 20, f"Expected ≥20 KV pairs, got {len(kv)}"
