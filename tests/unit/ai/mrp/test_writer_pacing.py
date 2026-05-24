"""
Unit tests for app/ai/mrp/writer_pacing.py:
  - LLMPacer: healthy vs ramped delay, success-streak heal, intermittent failures
  - ConsecutiveStubBreaker: trip-at-threshold, reset-on-success
  - is_stub_content: substring marker detection

Pure stdlib; no LLM/DB.
"""

import asyncio
import time

import pytest

from app.ai.mrp.writer_pacing import (
    STUB_MARKER,
    SUCCESS_STREAK_TO_HEAL,
    ConsecutiveStubBreaker,
    LLMPacer,
    is_stub_content,
)

# ---------------------------------------------------------------------------
# LLMPacer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pacer_healthy_uses_base_ms():
    pacer = LLMPacer(base_ms=50, fail_ms=500)
    t0 = time.monotonic()
    await pacer.wait()
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert 40 <= elapsed_ms < 200, f"healthy wait should be ~50ms, got {elapsed_ms:.0f}ms"


@pytest.mark.asyncio
async def test_pacer_skips_when_base_ms_zero():
    pacer = LLMPacer(base_ms=0, fail_ms=500)
    t0 = time.monotonic()
    await pacer.wait()
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert elapsed_ms < 30, f"base_ms=0 should skip sleep, got {elapsed_ms:.0f}ms"


@pytest.mark.asyncio
async def test_pacer_ramps_after_failure():
    pacer = LLMPacer(base_ms=0, fail_ms=80)
    pacer.report_outcome(False)
    t0 = time.monotonic()
    await pacer.wait()
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert 60 <= elapsed_ms < 250, f"ramped wait should be ~80ms, got {elapsed_ms:.0f}ms"


@pytest.mark.asyncio
async def test_pacer_resets_after_three_successes():
    pacer = LLMPacer(base_ms=0, fail_ms=80)
    pacer.report_outcome(False)  # ramp
    for _ in range(SUCCESS_STREAK_TO_HEAL):
        pacer.report_outcome(True)
    t0 = time.monotonic()
    await pacer.wait()
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert elapsed_ms < 30, f"should heal back to base_ms=0, got {elapsed_ms:.0f}ms"


@pytest.mark.asyncio
async def test_pacer_stays_ramped_with_intermittent_failures():
    pacer = LLMPacer(base_ms=0, fail_ms=60)
    pacer.report_outcome(False)
    pacer.report_outcome(True)
    pacer.report_outcome(True)
    pacer.report_outcome(False)  # streak broken — back to ramped
    t0 = time.monotonic()
    await pacer.wait()
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert elapsed_ms >= 40, f"intermittent failure keeps ramp, got {elapsed_ms:.0f}ms"


def test_pacer_success_streak_resets_on_failure():
    pacer = LLMPacer(base_ms=0, fail_ms=100)
    pacer.report_outcome(False)
    pacer.report_outcome(True)
    pacer.report_outcome(True)
    pacer.report_outcome(False)
    assert pacer._success_streak == 0
    assert pacer._ramped is True


# ---------------------------------------------------------------------------
# ConsecutiveStubBreaker
# ---------------------------------------------------------------------------


def test_breaker_trips_at_threshold():
    breaker = ConsecutiveStubBreaker(threshold=3)
    assert breaker.trip() is False  # count=1
    assert breaker.trip() is False  # count=2
    assert breaker.trip() is True   # count=3 → trip


def test_breaker_does_not_trip_below_threshold():
    breaker = ConsecutiveStubBreaker(threshold=5)
    for _ in range(4):
        assert breaker.trip() is False


def test_breaker_reset_zeros_counter():
    breaker = ConsecutiveStubBreaker(threshold=3)
    breaker.trip()
    breaker.trip()
    breaker.reset_on_success()
    assert breaker.trip() is False  # count=1 fresh after reset
    assert breaker.trip() is False  # count=2


def test_breaker_threshold_one_trips_immediately():
    breaker = ConsecutiveStubBreaker(threshold=1)
    assert breaker.trip() is True


# ---------------------------------------------------------------------------
# is_stub_content
# ---------------------------------------------------------------------------


def test_is_stub_detects_marker():
    assert is_stub_content(f"# Title\n\n{STUB_MARKER} model crashed)") is True


def test_is_stub_misses_real_content():
    assert is_stub_content("# Title\n\nReal page content here.") is False


def test_is_stub_handles_none():
    assert is_stub_content(None) is False


def test_is_stub_handles_empty():
    assert is_stub_content("") is False


# ---------------------------------------------------------------------------
# _safe_int_env (env clamping — H1/H2/H3 fixes)
# ---------------------------------------------------------------------------


def test_safe_int_env_returns_default_when_unset(monkeypatch):
    from app.ai.mrp.writer import _safe_int_env
    monkeypatch.delenv("ARKON_TEST_INT", raising=False)
    assert _safe_int_env("ARKON_TEST_INT", 5, minimum=1) == 5


def test_safe_int_env_clamps_below_minimum(monkeypatch):
    from app.ai.mrp.writer import _safe_int_env
    monkeypatch.setenv("ARKON_TEST_INT", "0")
    assert _safe_int_env("ARKON_TEST_INT", 3, minimum=1) == 3


def test_safe_int_env_clamps_negative(monkeypatch):
    from app.ai.mrp.writer import _safe_int_env
    monkeypatch.setenv("ARKON_TEST_INT", "-5")
    assert _safe_int_env("ARKON_TEST_INT", 3, minimum=1) == 3


def test_safe_int_env_falls_back_on_non_numeric(monkeypatch):
    from app.ai.mrp.writer import _safe_int_env
    monkeypatch.setenv("ARKON_TEST_INT", "abc")
    assert _safe_int_env("ARKON_TEST_INT", 7, minimum=1) == 7


def test_safe_int_env_accepts_valid_value(monkeypatch):
    from app.ai.mrp.writer import _safe_int_env
    monkeypatch.setenv("ARKON_TEST_INT", "12")
    assert _safe_int_env("ARKON_TEST_INT", 3, minimum=1) == 12


def test_safe_int_env_minimum_zero_allows_zero(monkeypatch):
    from app.ai.mrp.writer import _safe_int_env
    monkeypatch.setenv("ARKON_TEST_INT", "0")
    assert _safe_int_env("ARKON_TEST_INT", 5, minimum=0) == 0
