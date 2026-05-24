"""
RAM Guard — pre-flight memory availability check before loading LM models.

Uses ``psutil.virtual_memory().available`` (unified memory on M1/M2/M3 Mac).
Pure utility — no async, no DB, no side-effects beyond logging.

Design notes:
  - Fail-open on psutil errors (sandboxed envs may restrict process introspection).
  - Headroom is configurable per-call to override the instance default.
  - Logs at WARNING level when check fails so operators can diagnose OOM causes.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class RAMInsufficientError(Exception):
    """Raised by RAMGuard.assert_can_load when free RAM is below threshold.

    Attributes:
        required_gb: Estimated GB needed for the model.
        available_gb: Current free GB reported by psutil.
        headroom_gb: Headroom buffer that was applied.
    """

    def __init__(
        self,
        required_gb: float,
        available_gb: float,
        headroom_gb: float,
    ) -> None:
        self.required_gb = required_gb
        self.available_gb = available_gb
        self.headroom_gb = headroom_gb
        super().__init__(
            f"Insufficient RAM: need {required_gb:.1f} GB + {headroom_gb:.1f} GB "
            f"headroom = {required_gb + headroom_gb:.1f} GB, "
            f"but only {available_gb:.2f} GB available"
        )


# ---------------------------------------------------------------------------
# Guard class
# ---------------------------------------------------------------------------


class RAMGuard:
    """Pre-flight RAM availability checker.

    Args:
        headroom_gb: Default safety buffer in GB subtracted from available RAM.
                     Hardcoded default 2.0 matches design §5 for M1 Max 32GB.
    """

    def __init__(self, headroom_gb: float = 2.0) -> None:
        self._headroom_gb = headroom_gb

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_available_gb(self) -> float:
        """Return currently available RAM in GB. Fail-open on psutil error."""
        try:
            import psutil

            return psutil.virtual_memory().available / 1e9
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "RAMGuard: psutil.virtual_memory() failed (%s) — reporting available=999",
                exc,
            )
            return 999.0

    def check_can_load(
        self,
        estimated_gb: float,
        headroom_gb: Optional[float] = None,
    ) -> bool:
        """Return True if there is enough free RAM to load a model.

        Args:
            estimated_gb: Estimated model footprint in GB.
            headroom_gb: Override the instance-level headroom for this call.

        Returns:
            True if ``available - estimated_gb >= effective_headroom``.
            Returns True (fail-open) when psutil raises an exception — this
            prevents false-positive blocks in restricted sandbox environments.
        """
        effective_headroom = headroom_gb if headroom_gb is not None else self._headroom_gb

        try:
            import psutil

            available = psutil.virtual_memory().available / 1e9
        except Exception as exc:
            logger.warning(
                "RAMGuard: psutil unavailable (%s) — skipping check (fail-open)",
                exc,
            )
            return True

        can_load = (available - estimated_gb) >= effective_headroom
        if not can_load:
            logger.warning(
                "RAMGuard: insufficient RAM — need %.1f GB + %.1f GB headroom = %.1f GB, "
                "available %.2f GB",
                estimated_gb,
                effective_headroom,
                estimated_gb + effective_headroom,
                available,
            )
        return can_load

    def assert_can_load(
        self,
        estimated_gb: float,
        headroom_gb: Optional[float] = None,
    ) -> None:
        """Raise RAMInsufficientError if check_can_load returns False.

        Args:
            estimated_gb: Estimated model footprint in GB.
            headroom_gb: Override the instance-level headroom for this call.

        Raises:
            RAMInsufficientError: When free RAM is below the required threshold.
        """
        effective_headroom = headroom_gb if headroom_gb is not None else self._headroom_gb

        if not self.check_can_load(estimated_gb, effective_headroom):
            available = self.current_available_gb()
            raise RAMInsufficientError(
                required_gb=estimated_gb,
                available_gb=available,
                headroom_gb=effective_headroom,
            )
