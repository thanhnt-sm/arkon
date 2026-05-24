"""
LMSClientGuarded — LMSClient subclass with RAM pre-flight + OOM auto-fallback.

Two-layer protection:
  1. Pre-flight: check available RAM before calling LM Studio's load().
     If insufficient → try fallback_model_id (if provided) else raise.
  2. OOM counter: detect LM Studio OOM errors by regex on exception message.
     After 2 consecutive OOM hits for the same (source_id, phase) pair →
     switch permanently to fallback_model_id for that source. Counter is
     scoped per source so a transient pressure spike doesn't permanently
     downgrade all future sources.

OOM regex patterns (documented):
  ``(out of memory|oom|allocation failed|insufficient memory|metal.*memory|mps.*out)``
  - "out of memory"      — generic Python/system message
  - "oom"                — Linux kernel OOM killer log fragment
  - "allocation failed"  — malloc/Metal allocation path
  - "insufficient memory" — LM Studio v1.5 structured error text
  - "metal.*memory"      — macOS Metal GPU memory exhaustion
  - "mps.*out"           — PyTorch MPS backend OOM (seen in GGUF runners)

  LM Studio version compat note: error message formats vary between v0.3,
  v0.4, and v1.5.  The patterns above cover known formats.  If LM Studio
  changes its error schema in a future version, broaden by adding new
  alternatives to _OOM_PATTERN and re-deploy (no DB migration needed).

Usage:
    client = LMSClientGuarded(host, auth_token, ram_guard=RAMGuard(2.0))
    instance_id = await client.load(
        model_id="mlx-community/Qwen3-35B",
        load_options=LoadOptions(),
        source_id="wiki-job-uuid",
        phase="main_llm",
        estimated_ram_gb=21.0,
        fallback_model_id="mlx-community/Qwen3-32B-Instruct-4bit",
    )
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.ai.local_orchestrator.lms_client import LMSClient, LoadOptions
from app.ai.local_orchestrator.ram_guard import RAMGuard, RAMInsufficientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OOM detection regex (compiled once at import)
# ---------------------------------------------------------------------------

# See module docstring for per-pattern rationale and version compat notes.
_OOM_PATTERN = re.compile(
    r"(out of memory|oom|allocation failed|insufficient memory|metal.*memory|mps.*out)",
    re.IGNORECASE | re.DOTALL,
)


def _is_oom(exc: BaseException) -> bool:
    """Return True if the exception message matches any OOM pattern."""
    return bool(_OOM_PATTERN.search(str(exc)))


# ---------------------------------------------------------------------------
# Guarded client
# ---------------------------------------------------------------------------


class LMSClientGuarded(LMSClient):
    """LMSClient with RAM pre-flight check + OOM auto-fallback state machine.

    Args:
        host: LM Studio base URL (e.g. ``http://host.docker.internal:1234``).
        auth_token: Bearer token; empty string = no auth.
        default_timeout_s: Default request timeout in seconds.
        ram_guard: RAMGuard instance. Defaults to RAMGuard(headroom_gb=2.0).
    """

    def __init__(
        self,
        host: str,
        auth_token: str = "",
        default_timeout_s: float = 120.0,
        ram_guard: Optional[RAMGuard] = None,
    ) -> None:
        super().__init__(host=host, auth_token=auth_token, default_timeout_s=default_timeout_s)
        self._ram_guard: RAMGuard = ram_guard if ram_guard is not None else RAMGuard(headroom_gb=2.0)

        # Keyed by (source_id, phase) — counts consecutive OOM failures.
        self._oom_counter: dict[tuple[str, str], int] = {}
        # Keyed by (source_id, phase) — stores fallback model_id once switched.
        self._fallback_active: dict[tuple[str, str], str] = {}

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_active_model(self, source_id: str, phase: str, primary: str) -> str:
        """Return the model_id that should be used for predict() calls.

        After an OOM-triggered fallback switch, this returns the fallback
        model_id so that the router's predict() call targets the correct model.

        Args:
            source_id: Unique identifier for the processing job / source.
            phase: Phase slot name (e.g. ``"vision"``, ``"main_llm"``).
            primary: The normal (non-fallback) model_id.

        Returns:
            Fallback model_id if a switch is active, otherwise ``primary``.
        """
        return self._fallback_active.get((source_id, phase), primary)

    def reset_source(self, source_id: str) -> None:
        """Clear all OOM counters and fallback state for a completed source.

        Call this when processing for a source_id finishes so that transient
        memory pressure does not permanently downgrade subsequent sources.

        Args:
            source_id: The job/source whose counters should be cleared.
        """
        keys_to_remove = [k for k in self._oom_counter if k[0] == source_id]
        for k in keys_to_remove:
            del self._oom_counter[k]

        keys_to_remove = [k for k in self._fallback_active if k[0] == source_id]
        for k in keys_to_remove:
            del self._fallback_active[k]

        if keys_to_remove:
            logger.debug("LMSClientGuarded: reset_source source_id=%s", source_id)

    # ------------------------------------------------------------------
    # Override load()
    # ------------------------------------------------------------------

    async def load(  # type: ignore[override]
        self,
        model_id: str,
        load_options: LoadOptions,
        timeout_s: Optional[float] = None,
        *,
        source_id: str = "",
        phase: str = "",
        estimated_ram_gb: float = 0.0,
        fallback_model_id: str = "",
    ) -> str:
        """Load a model with RAM pre-flight check and OOM auto-fallback.

        Args:
            model_id: Primary model identifier string.
            load_options: LM Studio load configuration.
            timeout_s: Per-call timeout override.
            source_id: Opaque job/source identifier (for counter scoping).
            phase: Phase slot name (for counter scoping + logging).
            estimated_ram_gb: Expected RAM usage; ``0`` skips the pre-check.
            fallback_model_id: Model to try when pre-check or OOM blocks primary.

        Returns:
            instance_id string from LM Studio.

        Raises:
            RAMInsufficientError: Pre-check failed AND no fallback provided.
            Exception: Non-OOM load failure re-raised as-is.
        """
        key = (source_id, phase)

        # ----------------------------------------------------------------
        # Step 1: RAM pre-flight
        # ----------------------------------------------------------------
        if estimated_ram_gb > 0:
            try:
                self._ram_guard.assert_can_load(estimated_ram_gb)
            except RAMInsufficientError as ram_err:
                if fallback_model_id:
                    logger.warning(
                        "LMSClientGuarded: pre-flight RAM check failed for %s "
                        "(%.1f GB needed, %.2f GB free) — using fallback %s",
                        model_id,
                        estimated_ram_gb,
                        ram_err.available_gb,
                        fallback_model_id,
                    )
                    # Record the switch so get_active_model reflects it
                    if source_id and phase:
                        self._fallback_active[key] = fallback_model_id
                    return await super().load(fallback_model_id, load_options, timeout_s)
                else:
                    logger.error(
                        "LMSClientGuarded: pre-flight RAM check failed for %s "
                        "(%.1f GB needed, %.2f GB free) — no fallback available",
                        model_id,
                        estimated_ram_gb,
                        ram_err.available_gb,
                    )
                    raise

        # ----------------------------------------------------------------
        # Step 2: Attempt primary load
        # ----------------------------------------------------------------
        try:
            instance_id = await super().load(model_id, load_options, timeout_s)
            return instance_id
        except Exception as exc:
            if not _is_oom(exc):
                # Non-OOM failure — propagate immediately, no counter update.
                raise

            # OOM detected
            if not (source_id and phase):
                # No scoping info — cannot track, just re-raise.
                raise

            self._oom_counter[key] = self._oom_counter.get(key, 0) + 1
            count = self._oom_counter[key]
            logger.warning(
                "LMSClientGuarded: OOM on load model=%s source=%s phase=%s "
                "oom_count=%d",
                model_id,
                source_id,
                phase,
                count,
            )

            if count >= 2:
                if not fallback_model_id:
                    logger.error(
                        "LMSClientGuarded: OOM count=%d reached threshold but "
                        "no fallback_model_id configured — raising hard error",
                        count,
                    )
                    raise

                logger.warning(
                    "LMSClientGuarded: OOM threshold reached (count=%d) for "
                    "source=%s phase=%s — switching to fallback %s",
                    count,
                    source_id,
                    phase,
                    fallback_model_id,
                )
                self._fallback_active[key] = fallback_model_id
                # Attempt fallback load
                return await super().load(fallback_model_id, load_options, timeout_s)

            # count == 1 — first OOM, re-raise to let caller retry
            raise
