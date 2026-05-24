"""
Unit tests for app/ai/local_orchestrator/sampling_profiles.py

Coverage:
- SAMPLING_MAX has all 6 phase keys
- SAMPLING_OTHER has all 6 phase keys
- SAMPLING_MAX values match MAX_PRESET source of truth
- SAMPLING_OTHER: only temperature set, all other fields None
- SAMPLING_MAX['refine_write'].temperature == 0.7 (design spec)
- SAMPLING_OTHER['refine_write'].temperature == 0.7 (creative writing)
- SAMPLING_OTHER non-refine phases temperature == 0.3
- get_profile() dispatches correctly for both modes
- get_profile() raises ValueError for unknown mode
- get_profile() raises KeyError for unknown phase
- SamplingProfile.to_dict() omits None fields
- SamplingProfile is frozen (immutable)
"""

from __future__ import annotations

import pytest

from app.ai.local_orchestrator.presets import MAX_PRESET
from app.ai.local_orchestrator.sampling_profiles import (
    SAMPLING_MAX,
    SAMPLING_OTHER,
    SamplingProfile,
    get_profile,
)

_ALL_PHASES = frozenset(
    {"vision_caption", "map_extract", "reduce_plan", "refine_write", "verify_check", "digest_summary"}
)

# ---------------------------------------------------------------------------
# 1. Coverage — all 6 phases present
# ---------------------------------------------------------------------------


def test_sampling_max_has_all_phases():
    assert set(SAMPLING_MAX.keys()) == _ALL_PHASES


def test_sampling_other_has_all_phases():
    assert set(SAMPLING_OTHER.keys()) == _ALL_PHASES


# ---------------------------------------------------------------------------
# 2. SAMPLING_MAX values match MAX_PRESET
# ---------------------------------------------------------------------------


def test_sampling_max_refine_matches_preset():
    p = SAMPLING_MAX["refine_write"]
    preset = MAX_PRESET["sampling"]["refine"]
    assert p.temperature == preset["temperature"]
    assert p.top_p == preset["top_p"]
    assert p.top_k == preset["top_k"]
    assert p.min_p == preset["min_p"]
    assert p.repeat_penalty == preset["repeat_penalty"]


def test_sampling_max_map_matches_preset():
    p = SAMPLING_MAX["map_extract"]
    preset = MAX_PRESET["sampling"]["map"]
    assert p.temperature == preset["temperature"]
    assert p.top_p == preset["top_p"]
    assert p.top_k == preset["top_k"]
    assert p.min_p == preset["min_p"]


def test_sampling_max_verify_matches_preset():
    p = SAMPLING_MAX["verify_check"]
    preset = MAX_PRESET["sampling"]["verify"]
    assert p.temperature == preset["temperature"]
    assert p.top_p == preset["top_p"]


def test_sampling_max_vision_matches_preset():
    p = SAMPLING_MAX["vision_caption"]
    preset = MAX_PRESET["sampling"]["vision"]
    assert p.temperature == preset["temperature"]
    assert p.top_p == preset["top_p"]


# ---------------------------------------------------------------------------
# 3. Design spec: refine_write temperature
# ---------------------------------------------------------------------------


def test_sampling_max_refine_write_temperature_is_0_7():
    """Design doc §3 specifies refine temperature=0.7 for creative writing."""
    assert SAMPLING_MAX["refine_write"].temperature == pytest.approx(0.7)


def test_sampling_other_refine_write_temperature_is_0_7():
    """OTHER mode also uses 0.7 for refine to preserve writing quality."""
    assert SAMPLING_OTHER["refine_write"].temperature == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# 4. SAMPLING_OTHER — temperature-only, others None
# ---------------------------------------------------------------------------


def test_sampling_other_non_refine_phases_temperature_is_0_3():
    for phase in _ALL_PHASES - {"refine_write"}:
        assert SAMPLING_OTHER[phase].temperature == pytest.approx(0.3), (
            f"Expected temperature=0.3 for OTHER/{phase}"
        )


def test_sampling_other_all_phases_non_temp_fields_are_none():
    """OTHER mode must leave top_p, top_k, min_p, repeat_penalty, seed as None."""
    for phase, profile in SAMPLING_OTHER.items():
        assert profile.top_p is None, f"top_p should be None for OTHER/{phase}"
        assert profile.top_k is None, f"top_k should be None for OTHER/{phase}"
        assert profile.min_p is None, f"min_p should be None for OTHER/{phase}"
        assert profile.repeat_penalty is None, f"repeat_penalty should be None for OTHER/{phase}"
        assert profile.seed is None, f"seed should be None for OTHER/{phase}"


# ---------------------------------------------------------------------------
# 5. get_profile() dispatch
# ---------------------------------------------------------------------------


def test_get_profile_max_returns_sampling_max():
    for phase in _ALL_PHASES:
        assert get_profile(phase, "max") is SAMPLING_MAX[phase]


def test_get_profile_other_returns_sampling_other():
    for phase in _ALL_PHASES:
        assert get_profile(phase, "other") is SAMPLING_OTHER[phase]


def test_get_profile_invalid_mode_raises_value_error():
    with pytest.raises(ValueError, match="mode must be one of"):
        get_profile("refine_write", "turbo")


def test_get_profile_invalid_phase_raises_key_error():
    with pytest.raises(KeyError):
        get_profile("nonexistent_phase", "max")


# ---------------------------------------------------------------------------
# 6. SamplingProfile dataclass behaviour
# ---------------------------------------------------------------------------


def test_sampling_profile_to_dict_omits_none_fields():
    p = SamplingProfile(temperature=0.5, top_p=0.9)
    d = p.to_dict()
    assert "temperature" in d
    assert "top_p" in d
    assert "top_k" not in d
    assert "min_p" not in d
    assert "repeat_penalty" not in d
    assert "seed" not in d


def test_sampling_profile_to_dict_includes_all_set_fields():
    p = SamplingProfile(temperature=0.1, top_p=0.9, top_k=40, min_p=0.05, repeat_penalty=1.1, seed=42)
    d = p.to_dict()
    assert d == {
        "temperature": 0.1,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.05,
        "repeat_penalty": 1.1,
        "seed": 42,
    }


def test_sampling_profile_is_frozen():
    """frozen=True: attribute assignment must raise FrozenInstanceError."""
    p = SamplingProfile(temperature=0.5)
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        p.temperature = 0.9  # type: ignore[misc]


def test_sampling_profile_default_all_none():
    p = SamplingProfile()
    assert p.temperature is None
    assert p.top_p is None
    assert p.to_dict() == {}
