"""
Unit tests for app/ai/runtime_profile.py — derive() + LADDER allowlist.

Pure-function tests, no DB/network. Cloud config regression test asserts
exact pre-change constants (chunk=20k, concurrency=6, timeout=120, retry=3)
so an accidental edit to cloud branch fails loudly.
"""

import pytest

from app.ai.runtime_profile import (
    DEFAULT_CTX,
    ProfileConfig,
    _is_ladder_allowed,
    derive,
)


# ---------------------------------------------------------------------------
# derive() — cloud regression
# ---------------------------------------------------------------------------

def test_derive_cloud_exact_constants():
    """Cloud config must preserve pre-change constants (zero-regression gate)."""
    cfg = derive("cloud", 5_000)
    assert isinstance(cfg, ProfileConfig)
    assert cfg.concurrency == 6
    assert cfg.chunk_chars == 20_000
    assert cfg.extract_timeout_s == 120
    assert cfg.writer_timeout_s == 120
    assert cfg.retry_attempts == 3
    assert cfg.retry_backoff_max_s == 8
    assert cfg.embed_batch_size == 100


@pytest.mark.parametrize("ctx", [1_000, 5_000, 32_000, 5_000_000])
def test_derive_cloud_invariant_to_ctx(ctx):
    """Cloud config does not depend on context length."""
    cfg = derive("cloud", ctx)
    assert cfg.chunk_chars == 20_000
    assert cfg.concurrency == 6


# ---------------------------------------------------------------------------
# derive() — local profile thresholds (D6 mapping)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ctx,expected_chunk,expected_timeout", [
    (4_000, 5_000, 180),       # <=8k
    (8_000, 5_000, 180),       # boundary inclusive
    (12_000, 10_000, 180),     # <=16k
    (16_000, 10_000, 180),     # boundary inclusive
    (24_000, 18_000, 240),     # <=32k
    (32_000, 18_000, 240),     # boundary inclusive
    (64_000, 20_000, 240),     # >32k
    (128_000, 20_000, 240),    # large ctx
])
def test_derive_local_thresholds(ctx, expected_chunk, expected_timeout):
    cfg = derive("local", ctx)
    assert cfg.chunk_chars == expected_chunk
    assert cfg.extract_timeout_s == expected_timeout
    assert cfg.writer_timeout_s == expected_timeout
    # Local profile invariants
    assert cfg.concurrency == 1
    assert cfg.retry_attempts == 5
    assert cfg.retry_backoff_max_s == 60
    assert cfg.embed_batch_size == 16


def test_derive_local_default_ctx():
    """DEFAULT_CTX (32k) must land on the 18k chunk tier."""
    cfg = derive("local", DEFAULT_CTX)
    assert cfg.chunk_chars == 18_000


# ---------------------------------------------------------------------------
# LADDER allowlist — _is_ladder_allowed(base_url)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    # Literal allowed hosts
    ("http://localhost:1234", True),
    ("http://127.0.0.1:1234/v1", True),
    ("http://[::1]:1234", True),
    # LAN CIDR 192.168.0.0/16
    ("http://192.168.1.10:1234", True),
    ("http://192.168.255.255:1234", True),
    # Private CIDR 10.0.0.0/8
    ("http://10.5.1.1:1234", True),
    # Private CIDR 172.16.0.0/12
    ("http://172.16.0.1:1234", True),
    # Cloud markers — always denied
    ("https://api.openai.com/v1", False),
    ("https://api.anthropic.com", False),
    ("https://api.together.xyz", False),
    ("https://api.groq.com", False),
    # Public IPs — denied
    ("http://8.8.8.8:1234", False),
    ("http://1.1.1.1:1234", False),
    # Unknown hostnames — denied
    ("http://random-host.example.com", False),
])
def test_is_ladder_allowed(url, expected):
    assert _is_ladder_allowed(url) is expected


def test_is_ladder_allowed_none_url():
    """None URL → True (no host to probe; ladder gated by profile separately)."""
    assert _is_ladder_allowed(None) is True


def test_is_ladder_allowed_empty_url():
    """Empty string URL → True (same rationale as None)."""
    assert _is_ladder_allowed("") is True
