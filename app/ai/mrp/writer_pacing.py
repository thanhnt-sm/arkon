"""
MRP writer pacing primitives.

Per-batch instances (no global state) that wrap the writer's stub-failure
fan-out to absorb LM Studio crashes without producing a stub avalanche:

  - LLMPacer: adaptive inter-call delay. Healthy = base_ms; after a failure,
    ramps to fail_ms; resets to healthy after 3 consecutive successes.
  - ConsecutiveStubBreaker: counts consecutive stubs and signals abort when
    threshold reached. Reset on first non-stub success.

Both are stdlib-only and side-effect free (caller owns logging). See
plans/260524-1226-writer-sequential-and-lm-pacing/ for the spec.
"""

import asyncio
from dataclasses import dataclass

STUB_MARKER = "(Page generation failed:"
SUCCESS_STREAK_TO_HEAL = 3


@dataclass
class LLMPacer:
    base_ms: int = 0
    fail_ms: int = 3000
    _ramped: bool = False
    _success_streak: int = 0

    async def wait(self) -> None:
        delay = self.fail_ms if self._ramped else self.base_ms
        if delay > 0:
            await asyncio.sleep(delay / 1000)

    def report_outcome(self, success: bool) -> None:
        if success:
            self._success_streak += 1
            if self._success_streak >= SUCCESS_STREAK_TO_HEAL:
                self._ramped = False
        else:
            self._ramped = True
            self._success_streak = 0


@dataclass
class ConsecutiveStubBreaker:
    threshold: int = 3
    _count: int = 0

    def trip(self) -> bool:
        self._count += 1
        return self._count >= self.threshold

    def reset_on_success(self) -> None:
        self._count = 0


def is_stub_content(content_md: str | None) -> bool:
    return STUB_MARKER in (content_md or "")
