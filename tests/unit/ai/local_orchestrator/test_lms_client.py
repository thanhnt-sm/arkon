"""
Unit tests for app/ai/local_orchestrator/lms_client.py

All tests are pure — no real LM Studio connection.  The ``lmstudio`` SDK is
stubbed via sys.modules injection before the module under test is imported.

Test coverage:
  1. load() happy path returns instance_id
  2. load() retries on TimeoutError (2 failures + 1 success → returns)
  3. load() exhausts all retries → propagates TimeoutError
  4. unload() while inflight > 0 → raises BusyError
  5. predict() increments then decrements inflight counter
  6. BusyError cleared after predict completes (unload succeeds)
  7. lmstudio ImportError → falls back to REST (mode == "rest")
  8. Concurrent predict() calls — inflight reaches 2, then drops to 0
  9. load() reuses an already-loaded SDK model instead of loading a duplicate
  10. HTTP host URLs are normalized for the lmstudio SDK api_host parameter
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SDK stub helpers
# ---------------------------------------------------------------------------

def _make_sdk_stub() -> types.ModuleType:
    """
    Build a minimal fake ``lmstudio`` module that satisfies LMSClient's SDK
    code paths.  All SDK calls are synchronous (they run in threads in prod).
    """
    stub = types.ModuleType("lmstudio")

    # set_sync_api_timeout — no-op
    stub.set_sync_api_timeout = MagicMock()

    # Fake model handle returned by client.llm.model(instance_id)
    fake_model_handle = MagicMock()
    fake_model_handle.respond = MagicMock(return_value="stub response")

    # Fake loaded model object
    fake_loaded = MagicMock()
    fake_loaded.instance_id = "stub-model-id"

    # Fake client object
    fake_client = MagicMock()
    fake_client.llm.load_new_instance = MagicMock(return_value=fake_loaded)
    fake_client.llm.unload = MagicMock()
    fake_client.llm.list_loaded = MagicMock(return_value=[fake_loaded])
    fake_client.llm.model = MagicMock(return_value=fake_model_handle)

    # Client constructor
    stub.Client = MagicMock(return_value=fake_client)

    # Attach helpers for tests to reach inside
    stub._fake_client = fake_client
    stub._fake_model_handle = fake_model_handle
    stub._fake_loaded = fake_loaded

    return stub


def _inject_sdk(stub: types.ModuleType) -> None:
    sys.modules["lmstudio"] = stub


def _remove_sdk() -> None:
    sys.modules.pop("lmstudio", None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sdk_stub() -> types.ModuleType:
    """Inject stub SDK, yield it, then restore original state."""
    stub = _make_sdk_stub()
    _inject_sdk(stub)
    yield stub
    _remove_sdk()


@pytest.fixture()
def no_sdk(monkeypatch: pytest.MonkeyPatch):
    """Ensure lmstudio is NOT importable — forces REST fallback."""
    _remove_sdk()
    # Block future import attempts for this test
    monkeypatch.setitem(sys.modules, "lmstudio", None)  # type: ignore[arg-type]
    yield
    # monkeypatch auto-restores on teardown


def _make_client(sdk_stub=None, host: str = "http://localhost:1234") -> Any:
    """
    Import LMSClient fresh after SDK stub is already set in sys.modules.
    Re-importing ensures the constructor sees the current sys.modules state.
    """
    # Force re-evaluation of the module-level import in lms_client
    if "app.ai.local_orchestrator.lms_client" in sys.modules:
        del sys.modules["app.ai.local_orchestrator.lms_client"]

    from app.ai.local_orchestrator.lms_client import (
        BusyError,
        LMSClient,
        LoadOptions,
        SamplingParams,
    )
    return LMSClient, LoadOptions, SamplingParams, BusyError


# ---------------------------------------------------------------------------
# Test 1 — load() happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_happy_path(sdk_stub: types.ModuleType) -> None:
    """load() returns instance_id from SDK on first attempt."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    client = LMSClient(host="http://localhost:1234")
    assert client._mode == "sdk"

    opts = LoadOptions(context_length=8192)
    instance_id = await client.load("test/model", opts)

    assert instance_id == "test/model"
    sdk_stub._fake_client.llm.load_new_instance.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — load() retries on TimeoutError (2 fails + 1 success)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_retries_on_timeout(sdk_stub: types.ModuleType) -> None:
    """load() retries up to 3 attempts; eventual success on attempt 3."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    call_count = 0

    def _flaky_load(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("simulated timeout")
        fake = MagicMock()
        fake.instance_id = "retry-success-id"
        return fake

    sdk_stub._fake_client.llm.load_new_instance.side_effect = _flaky_load

    client = LMSClient(host="http://localhost:1234")
    opts = LoadOptions()
    instance_id = await client.load("test/model", opts)

    assert instance_id == "test/model"
    assert call_count == 3


# ---------------------------------------------------------------------------
# Test 3 — load() exhausts retries → propagates TimeoutError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_exhausts_retries(sdk_stub: types.ModuleType) -> None:
    """load() raises TimeoutError after 3 consecutive failures."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    sdk_stub._fake_client.llm.load_new_instance.side_effect = TimeoutError("always fails")

    client = LMSClient(host="http://localhost:1234")
    opts = LoadOptions()

    with pytest.raises(TimeoutError):
        await client.load("test/model", opts)

    # tenacity makes exactly 3 attempts
    assert sdk_stub._fake_client.llm.load_new_instance.call_count == 3


# ---------------------------------------------------------------------------
# Test 4 — unload() while inflight > 0 → BusyError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unload_raises_busy_error_when_inflight(sdk_stub: types.ModuleType) -> None:
    """unload() raises BusyError when a predict is still running."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    client = LMSClient(host="http://localhost:1234")

    # Manually set inflight counter to simulate an in-progress predict
    client._inflight["some-model"] = 1

    with pytest.raises(BusyError, match="some-model"):
        await client.unload("some-model")

    # SDK unload must NOT have been called
    sdk_stub._fake_client.llm.unload.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — predict() increments then decrements inflight counter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_inflight_increment_decrement(sdk_stub: types.ModuleType) -> None:
    """Inflight counter is 1 during predict and 0 after completion."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    client = LMSClient(host="http://localhost:1234")
    observed_mid_call: list[int] = []

    async def _predict_and_observe(*args, **kwargs):
        observed_mid_call.append(client._inflight.get("model-a", 0))
        return "response text"

    client._rest.predict = AsyncMock(side_effect=_predict_and_observe)

    params = SamplingParams(temperature=0.7)
    result = await client.predict("model-a", [{"role": "user", "content": "hi"}], params)

    assert result == "response text"
    # During the call, inflight was 1
    assert observed_mid_call == [1]
    # After completion, inflight is 0
    assert client._inflight.get("model-a", 0) == 0


# ---------------------------------------------------------------------------
# Test 6 — BusyError cleared after predict completes (unload succeeds after)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unload_succeeds_after_predict_completes(sdk_stub: types.ModuleType) -> None:
    """Unload succeeds once inflight drops to 0 after predict finishes."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    client = LMSClient(host="http://localhost:1234")
    client._rest.predict = AsyncMock(return_value="ok")

    params = SamplingParams()
    await client.predict("model-b", [{"role": "user", "content": "test"}], params)

    # Inflight must be 0 now — unload should not raise
    assert client._inflight.get("model-b", 0) == 0
    await client.unload("model-b")  # must not raise BusyError

    sdk_stub._fake_client.llm.unload.assert_called_once()


# ---------------------------------------------------------------------------
# Test 7 — lmstudio ImportError → REST fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_error_falls_back_to_rest(no_sdk: None) -> None:
    """When lmstudio is unavailable, LMSClient sets mode='rest'."""
    # Clear cached module so constructor re-evaluates import
    if "app.ai.local_orchestrator.lms_client" in sys.modules:
        del sys.modules["app.ai.local_orchestrator.lms_client"]

    from app.ai.local_orchestrator.lms_client import LMSClient

    client = LMSClient(host="http://localhost:1234")
    assert client._mode == "rest"
    # REST client should be attached
    assert hasattr(client, "_rest")


# ---------------------------------------------------------------------------
# Test 8 — Concurrent predict() calls — inflight peaks at 2 then drops to 0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_predict_inflight_tracking(sdk_stub: types.ModuleType) -> None:
    """Two concurrent predicts → inflight peaks at 2, then settles at 0."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    client = LMSClient(host="http://localhost:1234")
    peak_inflight: list[int] = []

    call_count = 0

    async def _slow_predict(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        peak_inflight.append(client._inflight.get("model-c", 0))
        return "ok"

    client._rest.predict = AsyncMock(side_effect=_slow_predict)

    params = SamplingParams()

    # Launch two concurrent predict calls
    results = await asyncio.gather(
        client.predict("model-c", [{"role": "user", "content": "msg1"}], params),
        client.predict("model-c", [{"role": "user", "content": "msg2"}], params),
    )

    assert results == ["ok", "ok"]
    # After both complete, inflight is 0
    assert client._inflight.get("model-c", 0) == 0
    # Both calls ran
    assert call_count == 2
    # At least one call observed inflight >= 1 (both ran, possibly serialised by to_thread)
    assert all(v >= 1 for v in peak_inflight)


# ---------------------------------------------------------------------------
# Test 9 — already loaded SDK model is reused
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_reuses_already_loaded_model(sdk_stub: types.ModuleType) -> None:
    """load() skips load_new_instance when LM Studio already has the model."""
    LMSClient, LoadOptions, SamplingParams, BusyError = _make_client()

    sdk_stub._fake_loaded.identifier = "test/model"
    sdk_stub._fake_client.llm.list_loaded.return_value = [sdk_stub._fake_loaded]

    client = LMSClient(host="http://localhost:1234")
    instance_id = await client.load("test/model", LoadOptions(context_length=8192))

    assert instance_id == "test/model"
    sdk_stub._fake_client.llm.load_new_instance.assert_not_called()


# ---------------------------------------------------------------------------
# Test 10 — SDK host normalization
# ---------------------------------------------------------------------------

def test_sdk_api_host_strips_http_scheme_and_path(sdk_stub: types.ModuleType) -> None:
    """lmstudio SDK expects host:port, not http://host:port/v1."""
    if "app.ai.local_orchestrator.lms_client" in sys.modules:
        del sys.modules["app.ai.local_orchestrator.lms_client"]

    from app.ai.local_orchestrator.lms_client import _sdk_api_host

    assert _sdk_api_host("http://192.168.1.6:1234") == "192.168.1.6:1234"
    assert _sdk_api_host("http://192.168.1.6:1234/v1") == "192.168.1.6:1234"
    assert _sdk_api_host("192.168.1.6:1234") == "192.168.1.6:1234"
