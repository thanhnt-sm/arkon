"""
Unit tests for app/ai/mrp/mapper.py — classify_pipeline_shape().

Boundaries (D3):
  <8k          → stuff
  8k–20k       → single_map
  20k–500k     → full_mrp
  >500k        → hierarchical
"""

import pytest

from app.ai.mrp.mapper import (
    SINGLE_MAP_THRESHOLD_CHARS,
    STUFF_THRESHOLD_CHARS,
    classify_pipeline_shape,
)


def test_threshold_constants():
    """Threshold constants must match D3 spec."""
    assert STUFF_THRESHOLD_CHARS == 8_000
    assert SINGLE_MAP_THRESHOLD_CHARS == 20_000


@pytest.mark.parametrize("char_count,expected", [
    # stuff: < 8k
    (0, "stuff"),
    (1, "stuff"),
    (7_999, "stuff"),
    # single_map: 8k–20k (n < 20k AND n >= 8k)
    (8_000, "single_map"),
    (10_000, "single_map"),
    (19_999, "single_map"),
    # full_mrp: 20k–500k
    (20_000, "full_mrp"),
    (100_000, "full_mrp"),
    (500_000, "full_mrp"),
    # hierarchical: > 500k
    (500_001, "hierarchical"),
    (1_000_000, "hierarchical"),
])
def test_classify_pipeline_shape(char_count, expected):
    text = "x" * char_count
    assert classify_pipeline_shape(text) == expected


def test_classify_empty_text():
    """Empty text → stuff (n=0 < STUFF_THRESHOLD_CHARS)."""
    assert classify_pipeline_shape("") == "stuff"
