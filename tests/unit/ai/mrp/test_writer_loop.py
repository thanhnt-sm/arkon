"""
Unit tests for app/ai/mrp/writer.py sequential refine loop:
  - per-page commit appends to plan_json._page_drafts
  - breaker trips after N consecutive stubs and aborts remaining work
  - pacer.wait() called between pages (not after last)
  - mixed real/stub sequences reset breaker on success

Mocks _write_one + plan + session — no LLM/DB.
"""

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from app.ai.mrp.writer import (
    PageWriteResult,
    WriterBatchIncomplete,
    _commit_draft,
    _run_refine_parallel,
    _run_refine_sequential,
)
from app.ai.mrp.writer_pacing import STUB_MARKER


def _make_result(slug: str, *, stub: bool = False) -> PageWriteResult:
    content = f"# {slug}\n\n{STUB_MARKER} forced)" if stub else f"# {slug}\n\nreal body"
    return PageWriteResult(
        slug=slug,
        title=slug.title(),
        page_type="concept",
        action="CREATE",
        content_md=content,
        summary=slug,
    )


@dataclass
class _FakePlan:
    plan_json: dict = field(default_factory=dict)


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:  # pragma: no cover — only hit on commit failure
        pass


def _make_specs(n: int) -> list[dict]:
    return [{"slug": f"page-{i}", "priority": i} for i in range(n)]


# ---------------------------------------------------------------------------
# _commit_draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_draft_appends_to_plan_json():
    plan = _FakePlan(plan_json={"existing_key": "kept"})
    session = _FakeSession()
    page = _make_result("alpha")

    await _commit_draft(session, plan, page)

    assert plan.plan_json["existing_key"] == "kept"
    drafts = plan.plan_json["_page_drafts"]
    assert len(drafts) == 1
    assert drafts[0]["slug"] == "alpha"
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_commit_draft_preserves_prior_drafts():
    plan = _FakePlan(plan_json={"_page_drafts": [{"slug": "prior"}]})
    session = _FakeSession()
    await _commit_draft(session, plan, _make_result("new"))
    slugs = [d["slug"] for d in plan.plan_json["_page_drafts"]]
    assert slugs == ["prior", "new"]


# ---------------------------------------------------------------------------
# _run_refine_sequential
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_success_commits_each_page(monkeypatch):
    monkeypatch.delenv("MRP_WRITER_PACE_BASE_MS", raising=False)
    monkeypatch.delenv("MRP_WRITER_PACE_FAIL_MS", raising=False)
    monkeypatch.delenv("MRP_WRITER_BREAKER_THRESHOLD", raising=False)

    specs = _make_specs(4)
    plan = _FakePlan()
    session = _FakeSession()
    write_one = AsyncMock(side_effect=[_make_result(s["slug"]) for s in specs])

    results = await _run_refine_sequential(specs, write_one, session, plan)

    assert len(results) == 4
    assert session.commit_calls == 4
    assert [d["slug"] for d in plan.plan_json["_page_drafts"]] == [s["slug"] for s in specs]


@pytest.mark.asyncio
async def test_one_stub_aborts_before_commit_phase(monkeypatch):
    monkeypatch.setenv("MRP_WRITER_PACE_BASE_MS", "0")
    monkeypatch.setenv("MRP_WRITER_PACE_FAIL_MS", "0")
    monkeypatch.setenv("MRP_WRITER_BREAKER_THRESHOLD", "3")

    specs = _make_specs(4)
    plan = _FakePlan()
    session = _FakeSession()
    write_one = AsyncMock(side_effect=[
        _make_result("page-0"),
        _make_result("page-1", stub=True),
        _make_result("page-2"),
        _make_result("page-3"),
    ])

    with pytest.raises(WriterBatchIncomplete) as exc_info:
        await _run_refine_sequential(specs, write_one, session, plan)

    assert exc_info.value.reason == "stub_drafts"
    assert exc_info.value.drafted == 3
    assert exc_info.value.expected == 4
    assert write_one.await_count == 4
    assert session.commit_calls == 4


@pytest.mark.asyncio
async def test_three_consecutive_stubs_trip_breaker_skips_remaining(monkeypatch):
    monkeypatch.setenv("MRP_WRITER_PACE_BASE_MS", "0")
    monkeypatch.setenv("MRP_WRITER_PACE_FAIL_MS", "0")
    monkeypatch.setenv("MRP_WRITER_BREAKER_THRESHOLD", "3")

    specs = _make_specs(6)
    plan = _FakePlan()
    session = _FakeSession()
    # Pages 0,1 real; 2,3,4 stub → breaker trips after page-4; page-5 never attempted.
    write_one = AsyncMock(side_effect=[
        _make_result("page-0"),
        _make_result("page-1"),
        _make_result("page-2", stub=True),
        _make_result("page-3", stub=True),
        _make_result("page-4", stub=True),
        _make_result("page-5"),  # should NOT be called
    ])

    with pytest.raises(WriterBatchIncomplete) as exc_info:
        await _run_refine_sequential(specs, write_one, session, plan)

    assert exc_info.value.drafted == 5
    assert exc_info.value.expected == 6
    assert write_one.await_count == 5
    drafts = [d["slug"] for d in plan.plan_json["_page_drafts"]]
    assert drafts == ["page-0", "page-1", "page-2", "page-3", "page-4"]


@pytest.mark.asyncio
async def test_stub_then_success_resets_breaker_but_still_aborts_before_commit(monkeypatch):
    monkeypatch.setenv("MRP_WRITER_PACE_BASE_MS", "0")
    monkeypatch.setenv("MRP_WRITER_PACE_FAIL_MS", "0")
    monkeypatch.setenv("MRP_WRITER_BREAKER_THRESHOLD", "3")

    specs = _make_specs(7)
    plan = _FakePlan()
    session = _FakeSession()
    # 2 stubs → success (resets) → 2 stubs → success → 1 stub. Never 3 in a row.
    write_one = AsyncMock(side_effect=[
        _make_result("page-0", stub=True),
        _make_result("page-1", stub=True),
        _make_result("page-2"),  # resets
        _make_result("page-3", stub=True),
        _make_result("page-4", stub=True),
        _make_result("page-5"),  # resets again
        _make_result("page-6", stub=True),
    ])

    with pytest.raises(WriterBatchIncomplete) as exc_info:
        await _run_refine_sequential(specs, write_one, session, plan)

    assert exc_info.value.reason == "stub_drafts"
    assert exc_info.value.drafted == 2
    assert exc_info.value.expected == 7
    assert write_one.await_count == 7


@pytest.mark.asyncio
async def test_write_one_returning_none_does_not_break_loop(monkeypatch):
    monkeypatch.setenv("MRP_WRITER_PACE_BASE_MS", "0")
    monkeypatch.setenv("MRP_WRITER_PACE_FAIL_MS", "0")

    specs = _make_specs(3)
    plan = _FakePlan()
    session = _FakeSession()
    write_one = AsyncMock(side_effect=[
        _make_result("page-0"),
        None,
        _make_result("page-2"),
    ])

    results = await _run_refine_sequential(specs, write_one, session, plan)

    assert len(results) == 2
    assert session.commit_calls == 2


@pytest.mark.asyncio
async def test_pacer_wait_called_between_pages_not_after_last(monkeypatch):
    # base_ms=50 → each gap adds ~50ms; with N=3 pages, expect 2 gaps (~100ms total),
    # NOT 3 (would be ~150ms). We assert under 150ms ceiling.
    import time
    monkeypatch.setenv("MRP_WRITER_PACE_BASE_MS", "50")
    monkeypatch.setenv("MRP_WRITER_PACE_FAIL_MS", "50")
    monkeypatch.setenv("MRP_WRITER_BREAKER_THRESHOLD", "99")

    specs = _make_specs(3)
    plan = _FakePlan()
    session = _FakeSession()
    write_one = AsyncMock(side_effect=[_make_result(s["slug"]) for s in specs])

    t0 = time.monotonic()
    await _run_refine_sequential(specs, write_one, session, plan)
    elapsed_ms = (time.monotonic() - t0) * 1000

    # 2 gaps × 50ms = 100ms; allow generous ceiling for CI jitter
    assert 80 <= elapsed_ms < 200, f"expected ~100ms (2 inter-page gaps), got {elapsed_ms:.0f}ms"


# ---------------------------------------------------------------------------
# _run_refine_parallel — escape hatch + breaker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_all_success_returns_all_results(monkeypatch):
    monkeypatch.setenv("MRP_WRITER_BREAKER_THRESHOLD", "3")
    specs = _make_specs(4)
    plan = _FakePlan()
    session = _FakeSession()
    write_one = AsyncMock(side_effect=[_make_result(s["slug"]) for s in specs])

    results = await _run_refine_parallel(
        concurrency=2,
        pages_spec=specs,
        write_one=write_one,
        session=session,
        plan=plan,
    )

    assert len(results) == 4
    assert {d["slug"] for d in plan.plan_json["_page_drafts"]} == {s["slug"] for s in specs}


@pytest.mark.asyncio
async def test_parallel_breaker_raises_writer_batch_incomplete(monkeypatch):
    monkeypatch.setenv("MRP_WRITER_BREAKER_THRESHOLD", "2")
    specs = _make_specs(6)
    plan = _FakePlan()
    session = _FakeSession()
    # Run with concurrency=1 to make ordering deterministic for the test.
    # First 2 stubs trip breaker; remaining 4 should be cancelled.
    write_one = AsyncMock(side_effect=[
        _make_result("page-0", stub=True),
        _make_result("page-1", stub=True),
        _make_result("page-2"),
        _make_result("page-3"),
        _make_result("page-4"),
        _make_result("page-5"),
    ])

    with pytest.raises(WriterBatchIncomplete) as exc_info:
        await _run_refine_parallel(
            concurrency=1,
            pages_spec=specs,
            write_one=write_one,
            session=session,
            plan=plan,
        )

    assert exc_info.value.drafted < exc_info.value.expected
    assert exc_info.value.expected == 6


# ---------------------------------------------------------------------------
# Sequential — threshold=1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breaker_threshold_one_trips_on_first_stub(monkeypatch):
    monkeypatch.setenv("MRP_WRITER_PACE_BASE_MS", "0")
    monkeypatch.setenv("MRP_WRITER_PACE_FAIL_MS", "0")
    monkeypatch.setenv("MRP_WRITER_BREAKER_THRESHOLD", "1")

    specs = _make_specs(5)
    plan = _FakePlan()
    session = _FakeSession()
    write_one = AsyncMock(side_effect=[
        _make_result("page-0"),
        _make_result("page-1", stub=True),
        _make_result("page-2"),  # should NOT be called
    ])

    with pytest.raises(WriterBatchIncomplete) as exc_info:
        await _run_refine_sequential(specs, write_one, session, plan)

    assert exc_info.value.drafted == 2
    assert write_one.await_count == 2
