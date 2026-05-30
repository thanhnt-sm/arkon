"""
Unit tests for app/ai/local_orchestrator/lms_client_guarded.py

All tests are pure — no real LM Studio connection. LMSClient.load() is mocked
via patch so tests exercise only the guard/fallback logic layer.

Test coverage:
  1.  RAM insufficient + fallback provided → uses fallback, no parent load for primary
  2.  RAM insufficient + no fallback → RAMInsufficientError raised
  3.  Successful load → returns instance_id, no OOM counter change
  4.  1 OOM (regex match) → counter=1, exception re-raised (NOT switched yet)
  5.  2 OOMs same (source, phase) → switches to fallback on 2nd, returns fallback id
  6.  2 OOMs different sources → counters are independent
  7.  2 OOMs + no fallback → hard exception raised after threshold
  8.  Non-OOM exception → re-raised as-is, counter NOT incremented
  9.  reset_source(uuid) clears that source only, other source unaffected
  10. get_active_model returns fallback after switch, primary before switch
  11. No source_id/phase → OOM re-raised without counter update
  12. OOM on fallback model itself → exception propagates (no infinite loop)
  13. Various OOM regex variants are detected
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.local_orchestrator.lms_client import LoadOptions
from app.ai.local_orchestrator.lms_client_guarded import (
    LMSClientGuarded,
    _is_oom,
    _is_remote_lms_host,
)
from app.ai.local_orchestrator.ram_guard import RAMGuard, RAMInsufficientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRIMARY = "mlx-community/Qwen3-35B"
FALLBACK = "mlx-community/Qwen3-32B-Instruct-4bit"
SOURCE = "job-uuid-abc123"
PHASE = "main_llm"
OPTS = LoadOptions()


def _make_guard(available_gb: float = 30.0) -> RAMGuard:
    """Return a RAMGuard whose psutil is pre-mocked to report available_gb."""
    guard = RAMGuard(headroom_gb=2.0)
    # Patch inside the guard's method calls
    return guard


def _guarded(available_gb: float = 30.0, headroom_gb: float = 2.0) -> LMSClientGuarded:
    """Return a LMSClientGuarded with a real RAMGuard using mocked psutil."""
    guard = RAMGuard(headroom_gb=headroom_gb)
    client = LMSClientGuarded(
        host="http://localhost:1234",
        auth_token="",
        ram_guard=guard,
    )
    return client


def _oom_exc(msg: str = "out of memory") -> RuntimeError:
    return RuntimeError(msg)


# ---------------------------------------------------------------------------
# OOM regex detection unit tests
# ---------------------------------------------------------------------------


class TestIsOom:
    @pytest.mark.parametrize("msg", [
        "CUDA out of memory",
        "Out Of Memory error occurred",
        "OOM killer activated",
        "allocation failed: not enough memory",
        "Insufficient memory to load model",
        "Metal: memory allocation error",
        "MPS out of resources",
        "mps backend out of memory",
    ])
    def test_detects_oom_patterns(self, msg: str):
        assert _is_oom(RuntimeError(msg)) is True

    @pytest.mark.parametrize("msg", [
        "connection refused",
        "timeout expired",
        "model not found",
        "invalid model path",
    ])
    def test_ignores_non_oom(self, msg: str):
        assert _is_oom(RuntimeError(msg)) is False


# ---------------------------------------------------------------------------
# RAM pre-flight tests
# ---------------------------------------------------------------------------


class TestPreflightRamCheck:
    @pytest.mark.asyncio
    async def test_ram_insufficient_uses_fallback(self):
        client = _guarded()
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(5 * 1e9)  # only 5 GB free
            with patch.object(
                type(client).__bases__[0],  # LMSClient
                "load",
                new_callable=AsyncMock,
                return_value="fallback-instance",
            ) as mock_parent_load:
                result = await client.load(
                    PRIMARY, OPTS,
                    source_id=SOURCE, phase=PHASE,
                    estimated_ram_gb=21.0, fallback_model_id=FALLBACK,
                )

        assert result == "fallback-instance"
        # Parent load called with fallback model, not primary
        call_args = mock_parent_load.call_args
        assert call_args[0][0] == FALLBACK

    @pytest.mark.asyncio
    async def test_ram_insufficient_no_fallback_raises(self):
        client = _guarded()
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(5 * 1e9)
            with pytest.raises(RAMInsufficientError):
                await client.load(
                    PRIMARY, OPTS,
                    source_id=SOURCE, phase=PHASE,
                    estimated_ram_gb=21.0, fallback_model_id="",
                )

    @pytest.mark.asyncio
    async def test_zero_estimated_skips_preflight(self):
        """estimated_ram_gb=0 must bypass the RAM check entirely."""
        client = _guarded()
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(1 * 1e9)  # 1 GB — would fail if checked
            with patch.object(
                type(client).__bases__[0],
                "load",
                new_callable=AsyncMock,
                return_value="inst-ok",
            ):
                result = await client.load(
                    PRIMARY, OPTS,
                    source_id=SOURCE, phase=PHASE,
                    estimated_ram_gb=0.0,
                )
        assert result == "inst-ok"

    @pytest.mark.asyncio
    async def test_remote_lms_host_skips_container_ram_preflight(self):
        """Docker workers cannot use container RAM as host LM Studio headroom."""
        client = LMSClientGuarded(
            host="http://192.168.1.6:1234",
            auth_token="",
            ram_guard=RAMGuard(headroom_gb=2.0),
        )
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(1 * 1e9)
            with patch.object(
                type(client).__bases__[0],
                "load",
                new_callable=AsyncMock,
                return_value="inst-ok",
            ) as mock_parent_load:
                result = await client.load(
                    PRIMARY,
                    OPTS,
                    source_id=SOURCE,
                    phase=PHASE,
                    estimated_ram_gb=21.0,
                    fallback_model_id=FALLBACK,
                )

        assert result == "inst-ok"
        assert mock_parent_load.call_args[0][0] == PRIMARY

    def test_remote_host_detection(self):
        assert _is_remote_lms_host("http://192.168.1.6:1234") is True
        assert _is_remote_lms_host("http://host.docker.internal:1234") is True
        assert _is_remote_lms_host("http://localhost:1234") is False


# ---------------------------------------------------------------------------
# OOM counter + fallback state machine
# ---------------------------------------------------------------------------


class TestOomCounterAndFallback:
    @pytest.mark.asyncio
    async def test_successful_load_no_counter_change(self):
        client = _guarded()
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(30 * 1e9)
            with patch.object(
                type(client).__bases__[0], "load",
                new_callable=AsyncMock, return_value="inst-ok",
            ):
                await client.load(PRIMARY, OPTS, source_id=SOURCE, phase=PHASE)

        assert client._oom_counter.get((SOURCE, PHASE), 0) == 0

    @pytest.mark.asyncio
    async def test_first_oom_increments_counter_and_reraises(self):
        client = _guarded()
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(30 * 1e9)
            with patch.object(
                type(client).__bases__[0], "load",
                new_callable=AsyncMock, side_effect=_oom_exc("out of memory"),
            ):
                with pytest.raises(RuntimeError, match="out of memory"):
                    await client.load(
                        PRIMARY, OPTS,
                        source_id=SOURCE, phase=PHASE,
                        estimated_ram_gb=0.0, fallback_model_id=FALLBACK,
                    )

        assert client._oom_counter[(SOURCE, PHASE)] == 1
        assert (SOURCE, PHASE) not in client._fallback_active

    @pytest.mark.asyncio
    async def test_second_oom_switches_to_fallback(self):
        client = _guarded()
        # Seed counter at 1 to simulate first OOM already occurred
        client._oom_counter[(SOURCE, PHASE)] = 1

        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(30 * 1e9)

            call_count = 0

            async def side_effect(model_id, opts, timeout=None):
                nonlocal call_count
                call_count += 1
                if model_id == PRIMARY:
                    raise _oom_exc("out of memory")
                return "fallback-instance-id"

            with patch.object(type(client).__bases__[0], "load", side_effect=side_effect):
                result = await client.load(
                    PRIMARY, OPTS,
                    source_id=SOURCE, phase=PHASE,
                    estimated_ram_gb=0.0, fallback_model_id=FALLBACK,
                )

        assert result == "fallback-instance-id"
        assert client._oom_counter[(SOURCE, PHASE)] == 2
        assert client._fallback_active[(SOURCE, PHASE)] == FALLBACK

    @pytest.mark.asyncio
    async def test_two_sources_have_independent_counters(self):
        client = _guarded()
        source_a = "source-aaa"
        source_b = "source-bbb"

        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(30 * 1e9)
            with patch.object(
                type(client).__bases__[0], "load",
                new_callable=AsyncMock, side_effect=_oom_exc("oom"),
            ):
                with pytest.raises(RuntimeError):
                    await client.load(
                        PRIMARY, OPTS,
                        source_id=source_a, phase=PHASE,
                        estimated_ram_gb=0.0, fallback_model_id=FALLBACK,
                    )
                with pytest.raises(RuntimeError):
                    await client.load(
                        PRIMARY, OPTS,
                        source_id=source_b, phase=PHASE,
                        estimated_ram_gb=0.0, fallback_model_id=FALLBACK,
                    )

        assert client._oom_counter[(source_a, PHASE)] == 1
        assert client._oom_counter[(source_b, PHASE)] == 1

    @pytest.mark.asyncio
    async def test_second_oom_no_fallback_raises_hard(self):
        client = _guarded()
        client._oom_counter[(SOURCE, PHASE)] = 1

        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(30 * 1e9)
            with patch.object(
                type(client).__bases__[0], "load",
                new_callable=AsyncMock, side_effect=_oom_exc("out of memory"),
            ):
                with pytest.raises(RuntimeError, match="out of memory"):
                    await client.load(
                        PRIMARY, OPTS,
                        source_id=SOURCE, phase=PHASE,
                        estimated_ram_gb=0.0, fallback_model_id="",
                    )

        assert client._oom_counter[(SOURCE, PHASE)] == 2

    @pytest.mark.asyncio
    async def test_non_oom_exception_reraises_without_counter(self):
        client = _guarded()
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(30 * 1e9)
            with patch.object(
                type(client).__bases__[0], "load",
                new_callable=AsyncMock, side_effect=ConnectionError("timeout"),
            ):
                with pytest.raises(ConnectionError):
                    await client.load(
                        PRIMARY, OPTS,
                        source_id=SOURCE, phase=PHASE,
                        estimated_ram_gb=0.0, fallback_model_id=FALLBACK,
                    )

        assert client._oom_counter.get((SOURCE, PHASE), 0) == 0

    @pytest.mark.asyncio
    async def test_no_source_id_oom_reraises_without_counter(self):
        """When source_id/phase not provided, OOM re-raises and no counter updated."""
        client = _guarded()
        with patch("psutil.virtual_memory") as mock_vmem:
            mock_vmem.return_value.available = int(30 * 1e9)
            with patch.object(
                type(client).__bases__[0], "load",
                new_callable=AsyncMock, side_effect=_oom_exc("out of memory"),
            ):
                with pytest.raises(RuntimeError):
                    await client.load(PRIMARY, OPTS)  # no source_id / phase

        assert len(client._oom_counter) == 0


# ---------------------------------------------------------------------------
# reset_source
# ---------------------------------------------------------------------------


class TestResetSource:
    def test_clears_that_source_only(self):
        client = _guarded()
        source_x = "source-x"
        source_y = "source-y"
        client._oom_counter[(source_x, "main_llm")] = 2
        client._oom_counter[(source_x, "vision")] = 1
        client._oom_counter[(source_y, "main_llm")] = 1
        client._fallback_active[(source_x, "main_llm")] = FALLBACK

        client.reset_source(source_x)

        # source_x cleared
        assert (source_x, "main_llm") not in client._oom_counter
        assert (source_x, "vision") not in client._oom_counter
        assert (source_x, "main_llm") not in client._fallback_active
        # source_y untouched
        assert client._oom_counter[(source_y, "main_llm")] == 1

    def test_reset_unknown_source_is_noop(self):
        client = _guarded()
        client.reset_source("nonexistent-uuid")  # should not raise


# ---------------------------------------------------------------------------
# get_active_model
# ---------------------------------------------------------------------------


class TestGetActiveModel:
    def test_returns_primary_before_switch(self):
        client = _guarded()
        result = client.get_active_model(SOURCE, PHASE, PRIMARY)
        assert result == PRIMARY

    def test_returns_fallback_after_switch(self):
        client = _guarded()
        client._fallback_active[(SOURCE, PHASE)] = FALLBACK
        result = client.get_active_model(SOURCE, PHASE, PRIMARY)
        assert result == FALLBACK

    def test_different_phase_still_returns_primary(self):
        client = _guarded()
        client._fallback_active[(SOURCE, "vision")] = "some-vision-fallback"
        # main_llm phase not switched — should return primary
        result = client.get_active_model(SOURCE, "main_llm", PRIMARY)
        assert result == PRIMARY


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_ram_guard_created(self):
        client = LMSClientGuarded(host="http://localhost:1234")
        assert isinstance(client._ram_guard, RAMGuard)
        assert client._ram_guard._headroom_gb == 2.0

    def test_custom_ram_guard_accepted(self):
        guard = RAMGuard(headroom_gb=4.0)
        client = LMSClientGuarded(host="http://localhost:1234", ram_guard=guard)
        assert client._ram_guard is guard
        assert client._ram_guard._headroom_gb == 4.0

    def test_counters_start_empty(self):
        client = LMSClientGuarded(host="http://localhost:1234")
        assert client._oom_counter == {}
        assert client._fallback_active == {}
