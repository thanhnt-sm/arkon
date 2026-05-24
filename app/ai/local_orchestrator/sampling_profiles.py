"""
Per-phase sampling profiles for the Local AI Orchestrator.

Two profile sets:
  SAMPLING_MAX   — full tuned values for MAX mode (from MAX_PRESET)
  SAMPLING_OTHER — minimal: only temperature per phase, all other fields None
                   (lets LM Studio apply its model defaults)

Phase keys: vision_caption, map_extract, reduce_plan, refine_write,
            verify_check, digest_summary
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.ai.local_orchestrator.presets import MAX_PRESET

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SamplingProfile:
    """Immutable per-phase sampling configuration.

    Fields not set (None) are omitted from LM Studio requests, allowing the
    model's own defaults to apply. This is intentional for OTHER mode.
    """

    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    repeat_penalty: Optional[float] = None
    seed: Optional[int] = None

    def to_dict(self) -> dict:
        """Return only the fields that are explicitly set (non-None)."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


# ---------------------------------------------------------------------------
# MAX mode — all tuned values from MAX_PRESET
# ---------------------------------------------------------------------------

_s = MAX_PRESET["sampling"]

SAMPLING_MAX: dict[str, SamplingProfile] = {
    "vision_caption": SamplingProfile(
        temperature=_s["vision"]["temperature"],
        top_p=_s["vision"]["top_p"],
    ),
    "map_extract": SamplingProfile(
        temperature=_s["map"]["temperature"],
        top_p=_s["map"]["top_p"],
        top_k=_s["map"]["top_k"],
        min_p=_s["map"]["min_p"],
    ),
    "reduce_plan": SamplingProfile(
        temperature=_s["reduce"]["temperature"],
        top_p=_s["reduce"]["top_p"],
        top_k=_s["reduce"]["top_k"],
        min_p=_s["reduce"]["min_p"],
    ),
    "refine_write": SamplingProfile(
        temperature=_s["refine"]["temperature"],
        top_p=_s["refine"]["top_p"],
        top_k=_s["refine"]["top_k"],
        min_p=_s["refine"]["min_p"],
        repeat_penalty=_s["refine"]["repeat_penalty"],
    ),
    "verify_check": SamplingProfile(
        temperature=_s["verify"]["temperature"],
        top_p=_s["verify"]["top_p"],
        top_k=_s["verify"]["top_k"],
        min_p=_s["verify"]["min_p"],
    ),
    "digest_summary": SamplingProfile(
        temperature=_s["digest"]["temperature"],
        top_p=_s["digest"]["top_p"],
        top_k=_s["digest"]["top_k"],
        min_p=_s["digest"]["min_p"],
    ),
}

# ---------------------------------------------------------------------------
# OTHER mode — temperature-only; all other fields None (model defaults apply)
# ---------------------------------------------------------------------------
# REFINE uses 0.7 for creative long-form writing variety.
# All other phases use 0.3 (moderate, conservative fallback).

SAMPLING_OTHER: dict[str, SamplingProfile] = {
    "vision_caption": SamplingProfile(temperature=0.3),
    "map_extract": SamplingProfile(temperature=0.3),
    "reduce_plan": SamplingProfile(temperature=0.3),
    "refine_write": SamplingProfile(temperature=0.7),
    "verify_check": SamplingProfile(temperature=0.3),
    "digest_summary": SamplingProfile(temperature=0.3),
}

_VALID_PHASES = frozenset(SAMPLING_MAX.keys())
_VALID_MODES = frozenset({"max", "other"})

# ---------------------------------------------------------------------------
# Dispatch helper
# ---------------------------------------------------------------------------


def get_profile(phase: str, mode: str) -> SamplingProfile:
    """Return the SamplingProfile for the given phase and mode.

    Args:
        phase: One of the 6 phase keys (e.g. "refine_write", "map_extract").
        mode:  "max" or "other".

    Returns:
        The matching SamplingProfile (immutable dataclass).

    Raises:
        KeyError: phase is not a recognised phase key.
        ValueError: mode is not "max" or "other".
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}")
    if phase not in _VALID_PHASES:
        raise KeyError(f"Unknown phase {phase!r}. Valid phases: {sorted(_VALID_PHASES)}")

    return SAMPLING_MAX[phase] if mode == "max" else SAMPLING_OTHER[phase]
