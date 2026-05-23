"""
LLM Runtime Profile — single source of truth for dynamic LLM config.

Maps `llm_profile` (local/cloud) + probed `context_length` + `model_name`
to derived runtime settings (concurrency, chunk size, timeouts, retries).

Cache + asyncio lock live at module scope so ProviderRegistry instances
(per request) share the same view. Invalidated explicitly by the admin
PATCH endpoint so toggle takes effect on next ingest, not after 60s TTL.

Design notes:
- Profile=local: serial extraction, longer timeouts, more retries, test-ping
  ladder probes ctx length when /v1/models doesn't report it.
- Profile=cloud: parallel extraction at existing 6-way concurrency, short
  timeouts, fewer retries. Ladder HARD-GATED off to avoid token cost spam.
- LADDER allowlist defends against an operator accidentally pointing a
  local profile at a billable cloud host.
"""

from __future__ import annotations

import asyncio
import ipaddress
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from loguru import logger

# Default context length when /v1/models lacks the field and ladder is
# unavailable (cloud profile, or local pre-probe).
DEFAULT_CTX = 32_000

# Cache TTL — 60s normal lifetime. Invalidated immediately by admin PATCH.
_CACHE_TTL_SEC = 60.0

# LADDER allowlist: only probe these hosts. Matches
# `[[feedback-squid-acl-range]]` 192.168.0.0/16 LAN preference.
_LADDER_ALLOWED_LITERAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_LADDER_ALLOWED_CIDRS = (
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
)

# Hosts that indicate a cloud install regardless of profile column.
_CLOUD_HOST_MARKERS = (
    "openai.com",
    "anthropic.com",
    "togetherapi.com",
    "together.xyz",
    "groq.com",
)


# ---------------------------------------------------------------------------
# Derived config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProfileConfig:
    """Derived knobs consumed by mapper/pipeline/openai_provider."""

    concurrency: int
    chunk_chars: int
    extract_timeout_s: int
    writer_timeout_s: int
    retry_attempts: int
    retry_backoff_max_s: int
    embed_batch_size: int


@dataclass(frozen=True)
class LLMRuntimeProfile:
    """Immutable per-request snapshot of profile + derived knobs."""

    profile: str  # "local" | "cloud"
    context_length: int
    model_name: Optional[str]
    base_url: Optional[str]
    cfg: ProfileConfig

    @property
    def is_local(self) -> bool:
        return self.profile == "local"

    @property
    def is_cloud(self) -> bool:
        return self.profile == "cloud"

    # Convenience accessors (mapper/pipeline read these directly).
    @property
    def concurrency(self) -> int:
        return self.cfg.concurrency

    @property
    def chunk_chars(self) -> int:
        return self.cfg.chunk_chars

    @property
    def extract_timeout_s(self) -> int:
        return self.cfg.extract_timeout_s

    @property
    def writer_timeout_s(self) -> int:
        return self.cfg.writer_timeout_s


# ---------------------------------------------------------------------------
# Derive mapping (cloud preserves existing constants for zero regression)
# ---------------------------------------------------------------------------

def derive(profile: str, ctx: int) -> ProfileConfig:
    """Map (profile, context_length) → ProfileConfig."""
    if profile == "cloud":
        # Match pre-change constants: chunk=20k, concurrency=6, timeout=120
        return ProfileConfig(
            concurrency=6,
            chunk_chars=20_000,
            extract_timeout_s=120,
            writer_timeout_s=120,
            retry_attempts=3,
            retry_backoff_max_s=8,
            embed_batch_size=100,
        )

    # Local profile — fixed mapping per D6
    if ctx <= 8_000:
        chunk, timeout = 5_000, 180
    elif ctx <= 16_000:
        chunk, timeout = 10_000, 180
    elif ctx <= 32_000:
        chunk, timeout = 18_000, 240
    else:
        chunk, timeout = 20_000, 240
    return ProfileConfig(
        concurrency=1,
        chunk_chars=chunk,
        extract_timeout_s=timeout,
        writer_timeout_s=timeout,
        retry_attempts=5,
        retry_backoff_max_s=60,
        embed_batch_size=16,
    )


# ---------------------------------------------------------------------------
# Module-scope cache + lock
# ---------------------------------------------------------------------------

_PROFILE_CACHE: dict[str, object] = {}  # keys: profile, ctx, model, base_url, ts
_PROFILE_LOCK = asyncio.Lock()


def invalidate() -> None:
    """Clear the cache so the next call re-probes. Called by admin PATCH."""
    global _PROFILE_CACHE
    _PROFILE_CACHE = {}
    logger.info("[runtime_profile] cache invalidated")


def _is_ladder_allowed(base_url: Optional[str]) -> bool:
    """Defense-in-depth: never probe an external host even if profile=local."""
    if not base_url:
        return True  # No base_url → assume OpenAI default; ladder is gated by profile anyway
    try:
        host = urlparse(base_url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    if host in _LADDER_ALLOWED_LITERAL_HOSTS:
        return True
    # Cloud markers always denied
    if any(h in host for h in _CLOUD_HOST_MARKERS):
        return False
    # Try CIDR match (LAN ranges)
    try:
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _LADDER_ALLOWED_CIDRS)
    except ValueError:
        pass
    # Reject anything that's not explicitly allowed.
    return False


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------

async def _probe_model_metadata(client, base_url: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    """
    GET /v1/models — best-effort. Returns (model_name, context_length).
    Both can be None if endpoint is silent or unreachable.
    """
    try:
        result = await asyncio.wait_for(client.models.list(), timeout=3.0)
    except Exception as exc:
        logger.warning(f"[runtime_profile] /v1/models probe failed: {exc}")
        return None, None

    data = getattr(result, "data", None) or []
    if not data:
        return None, None

    first = data[0]
    model_name = getattr(first, "id", None)
    # vLLM/LM Studio may surface ctx via `context_length`, `n_ctx`, or
    # `meta.context_length`. Best-effort extraction.
    ctx = None
    for attr in ("context_length", "max_context_length", "n_ctx"):
        ctx = getattr(first, attr, None)
        if ctx:
            break
    if ctx is None:
        meta = getattr(first, "meta", None) or {}
        if isinstance(meta, dict):
            ctx = meta.get("context_length") or meta.get("n_ctx")

    return (model_name, int(ctx) if ctx else None)


async def _test_ping_ladder(
    client, model_id: str, levels=(4_000, 8_000, 16_000, 32_000)
) -> int:
    """
    Walk a ladder of escalating prompt sizes; return the largest that
    succeeds. Each ping uses `"x " * (n*2)` because BPE compresses ~2:1, so
    we need ~2x chars to test n tokens of capacity.
    """
    last_ok = levels[0]
    for n in levels:
        prompt = "x " * (n * 2)  # ~n tokens after BPE
        try:
            await asyncio.wait_for(
                client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                    temperature=0,
                ),
                timeout=15,
            )
            last_ok = n
            logger.info(f"[runtime_profile] ladder ping ok at {n} tokens")
        except Exception as exc:
            logger.info(f"[runtime_profile] ladder ping FAILED at {n} tokens: {exc}")
            break
    return last_ok


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def ensure_profile_loaded(
    config_service,
    llm_client=None,
    llm_model_id: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> LLMRuntimeProfile:
    """
    Resolve the active LLMRuntimeProfile. Cached for 60s by
    (profile, model_name, base_url). Probe runs at most once at a time
    via module-scope asyncio.Lock.

    `config_service` must be a ConfigService bound to a live AsyncSession.
    `llm_client` is optional; if None, probing/ladder are skipped (cloud
    or first-load short circuit).
    """
    now = time.monotonic()

    # Fast path — cache hit
    cached = _PROFILE_CACHE.get("profile")
    if cached is not None:
        ts = _PROFILE_CACHE.get("ts", 0)
        if isinstance(ts, (int, float)) and (now - ts) < _CACHE_TTL_SEC:
            # Only invalidate on model change; base_url change implies redeploy
            if _PROFILE_CACHE.get("model") == llm_model_id or llm_model_id is None:
                return cached  # type: ignore[return-value]

    async with _PROFILE_LOCK:
        # Re-check under lock (another waiter may have populated)
        cached = _PROFILE_CACHE.get("profile")
        if cached is not None:
            ts = _PROFILE_CACHE.get("ts", 0)
            if isinstance(ts, (int, float)) and (now - ts) < _CACHE_TTL_SEC:
                if _PROFILE_CACHE.get("model") == llm_model_id or llm_model_id is None:
                    return cached  # type: ignore[return-value]

        # Resolve profile value (DB only — env override dropped per D1)
        profile_raw = (await config_service.get("llm_profile")) or "local"
        profile = profile_raw.strip().lower()
        if profile not in ("local", "cloud"):
            logger.warning(f"[runtime_profile] unknown profile {profile_raw!r}, defaulting to local")
            profile = "local"

        # Determine context length
        cached_ctx_str = await config_service.get("llm_context_length")
        cached_model_str = await config_service.get("llm_model_name")
        ctx: Optional[int] = None
        model_name: Optional[str] = None

        if cached_ctx_str and cached_model_str and cached_model_str == (llm_model_id or cached_model_str):
            try:
                ctx = int(cached_ctx_str)
                model_name = cached_model_str
            except ValueError:
                ctx = None

        # Probe metadata for local profile when no cached ctx or model changed
        need_probe = (
            llm_client is not None
            and profile == "local"
            and (ctx is None or (llm_model_id and cached_model_str != llm_model_id))
        )

        if need_probe:
            probed_model, probed_ctx = await _probe_model_metadata(llm_client, llm_base_url)
            if probed_model:
                model_name = probed_model
            if probed_ctx:
                ctx = probed_ctx
            # Ladder fallback if still no ctx and base URL is in the allowlist
            if ctx is None and _is_ladder_allowed(llm_base_url) and (model_name or llm_model_id):
                try:
                    ctx = await _test_ping_ladder(llm_client, model_name or llm_model_id or "")
                except Exception as exc:
                    logger.warning(f"[runtime_profile] ladder probe failed: {exc}")
                    ctx = DEFAULT_CTX
            # Persist probe result
            if ctx is not None:
                await config_service.set("llm_context_length", str(ctx))
            if model_name:
                await config_service.set("llm_model_name", model_name)

        if ctx is None:
            ctx = DEFAULT_CTX

        cfg = derive(profile, ctx)
        prof = LLMRuntimeProfile(
            profile=profile,
            context_length=ctx,
            model_name=model_name or llm_model_id,
            base_url=llm_base_url,
            cfg=cfg,
        )
        _PROFILE_CACHE["profile"] = prof
        _PROFILE_CACHE["model"] = prof.model_name
        _PROFILE_CACHE["ts"] = now

        logger.info(
            f"[profile={prof.profile}, ctx={prof.context_length}, "
            f"chunk={prof.chunk_chars}, concurrency={prof.concurrency}, "
            f"retry={prof.cfg.retry_attempts}]"
        )
        return prof


def looks_like_cloud_host(base_url: Optional[str]) -> bool:
    """Helper for migration auto-detect: True iff base_url is a known cloud host."""
    if not base_url:
        return False
    host = (urlparse(base_url).hostname or "").lower()
    return any(marker in host for marker in _CLOUD_HOST_MARKERS)
