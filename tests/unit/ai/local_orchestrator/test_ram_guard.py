"""
Unit tests for app/ai/local_orchestrator/ram_guard.py

All tests mock psutil.virtual_memory to avoid real hardware dependency.
Test coverage:
  1. check_can_load → True when available − estimated >= headroom
  2. check_can_load → False when available − estimated < headroom
  3. check_can_load → True when psutil raises (fail-open)
  4. assert_can_load raises RAMInsufficientError with informative message
  5. assert_can_load passes silently when RAM is sufficient
  6. current_available_gb returns float
  7. current_available_gb returns 999.0 on psutil error (fail-open)
  8. Custom headroom override per check_can_load call
  9. Custom headroom override per assert_can_load call
  10. Error message includes required_gb, available_gb, headroom_gb
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ai.local_orchestrator.ram_guard import RAMGuard, RAMInsufficientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_vmem(available_bytes: int) -> MagicMock:
    """Build a fake psutil virtual_memory() result."""
    vmem = MagicMock()
    vmem.available = available_bytes
    return vmem


def _gb(gb: float) -> int:
    return int(gb * 1e9)


# ---------------------------------------------------------------------------
# check_can_load
# ---------------------------------------------------------------------------


class TestCheckCanLoad:
    def test_returns_true_when_sufficient(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(25.0))):
            # 25 available − 20 estimated = 5 >= 2 headroom → True
            assert guard.check_can_load(20.0) is True

    def test_returns_false_when_insufficient(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(21.0))):
            # 21 available − 20 estimated = 1 < 2 headroom → False
            assert guard.check_can_load(20.0) is False

    def test_returns_false_at_exact_boundary(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(21.999))):
            # 21.999 − 20 = 1.999 < 2 → False
            assert guard.check_can_load(20.0) is False

    def test_returns_true_at_exact_headroom(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(22.0))):
            # 22 − 20 = 2.0 >= 2 → True
            assert guard.check_can_load(20.0) is True

    def test_fail_open_on_psutil_exception(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", side_effect=PermissionError("sandbox")):
            # psutil blocked → fail open → True
            assert guard.check_can_load(20.0) is True

    def test_headroom_override_per_call(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(21.0))):
            # With default headroom=2.0 → False (21 − 20 = 1 < 2)
            assert guard.check_can_load(20.0) is False
            # With override headroom=0.5 → True (21 − 20 = 1 >= 0.5)
            assert guard.check_can_load(20.0, headroom_gb=0.5) is True

    def test_large_model_with_plenty_of_ram(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(30.0))):
            assert guard.check_can_load(19.0) is True

    def test_zero_estimated_always_passes(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(5.0))):
            # 5 − 0 = 5 >= 2 → True
            assert guard.check_can_load(0.0) is True


# ---------------------------------------------------------------------------
# assert_can_load
# ---------------------------------------------------------------------------


class TestAssertCanLoad:
    def test_raises_when_insufficient(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(21.0))):
            with pytest.raises(RAMInsufficientError) as exc_info:
                guard.assert_can_load(20.0)

        err = exc_info.value
        assert err.required_gb == 20.0
        assert err.headroom_gb == 2.0
        # available_gb comes from a second psutil call in assert_can_load
        assert isinstance(err.available_gb, float)

    def test_error_message_is_informative(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(15.0))):
            with pytest.raises(RAMInsufficientError) as exc_info:
                guard.assert_can_load(20.0)

        msg = str(exc_info.value)
        assert "20.0" in msg  # required
        assert "2.0" in msg   # headroom
        assert "GB" in msg

    def test_does_not_raise_when_sufficient(self):
        guard = RAMGuard(headroom_gb=2.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(25.0))):
            guard.assert_can_load(20.0)  # should not raise

    def test_headroom_override_per_call(self):
        guard = RAMGuard(headroom_gb=5.0)
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(22.0))):
            # Default headroom=5.0: 22 − 20 = 2 < 5 → raises
            with pytest.raises(RAMInsufficientError):
                guard.assert_can_load(20.0)
            # Override headroom=1.0: 22 − 20 = 2 >= 1 → passes
            guard.assert_can_load(20.0, headroom_gb=1.0)


# ---------------------------------------------------------------------------
# current_available_gb
# ---------------------------------------------------------------------------


class TestCurrentAvailableGb:
    def test_returns_float(self):
        guard = RAMGuard()
        with patch("psutil.virtual_memory", return_value=_mock_vmem(_gb(16.0))):
            result = guard.current_available_gb()
        assert isinstance(result, float)
        assert abs(result - 16.0) < 0.01

    def test_fail_open_returns_999(self):
        guard = RAMGuard()
        with patch("psutil.virtual_memory", side_effect=OSError("no access")):
            result = guard.current_available_gb()
        assert result == 999.0


# ---------------------------------------------------------------------------
# RAMInsufficientError attributes
# ---------------------------------------------------------------------------


class TestRAMInsufficientError:
    def test_attributes_set_correctly(self):
        err = RAMInsufficientError(required_gb=21.0, available_gb=5.5, headroom_gb=2.0)
        assert err.required_gb == 21.0
        assert err.available_gb == 5.5
        assert err.headroom_gb == 2.0
        assert "21.0" in str(err)
        assert "5.5" in str(err) or "available" in str(err).lower()

    def test_is_exception(self):
        err = RAMInsufficientError(21.0, 5.0, 2.0)
        assert isinstance(err, Exception)
