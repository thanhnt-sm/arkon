---
title: "MRP Writer Sequential + Per-Page Commit Execution"
date: 2026-05-24
plan: plans/260524-1226-writer-sequential-and-lm-pacing/
mode: /ck:cook --auto
commits: 5661271 (feat(mrp): sequential writer + per-page commit + stub breaker)
tests: 31 unit tests all pass; 2 pre-existing failures in test_embedding_catalog.py (unrelated)
duration: ~3h
---

# MRP Writer Sequential + Per-Page Commit — Code Review Catch & Resume Logic

## Scope

Six-phase plan executed as seven (Phase 07 added post-code-review). Implemented sequential writer with per-page batch commit, stub-breaking on `refine_timeout`, and idempotent resume logic. Single commit landed; 31 new unit tests pass; 2 pre-existing test failures untouched.

## Three Critical Lessons

### L1: Per-Page Persistence Necessary, Not Sufficient — Consumer-Side Validation Missed

**The catch:** Code-reviewer flagged that `pipeline.py:539-541` unconditionally advanced `pipeline_phase='verify'` after `run_refine_phase()` returned, regardless of whether the breaker tripped. If a writer batch hit timeout and stubs persisted to `_page_drafts`, the partial wiki (with stubs) would ship silently through VERIFY/COMMIT as `status='ready'`. Per-page writes don't prevent all-or-nothing loss if downstream phases treat "function returned" as "succeeded."

**Fix:** Raise `WriterBatchIncomplete` on stub detection; catch in `pipeline.py`, don't advance phase. Small code change; enormous scope implication.

**Lesson:** Brainstorm must trace not just persistence strategy (per-page) but who consumes the persistence state and what they infer from it. A single-bit "completion" downstream is incompatible with incremental persistence unless consumers distinguish "done" from "partial."

### L2: "Drafted" is Two States — Slug-Skip Resume Breaks After Breaker

**The tension:** Idempotent resume via slug-skip seemed obviously correct (retry only un-drafted slugs). But after breaker trip, `_page_drafts` contains real pages AND stubs. Skipping ALL drafted slugs meant stubs persisted forever.

**Solution:** Split resume logic: keep real pages, prune stubs, re-attempt them. Distinguish "successfully drafted" from "tried, failed, stubbed."

**Lesson:** When persistence is incremental, every consumer of the persisted state must distinguish "done" from "tried and failed." A retry loop that skips "attempted" without examining outcome is a footgun. This is orthogonal to the per-page write problem — it's a state-machine gap.

### L3: Convention Drift on Status Values — "failed" vs "error" Silently Breaks Retry Flow

**The drift:** `source.status='failed'` lived in `pipeline.py`'s LMStudioDownError handler since forever. But `retry-sources.sh` AUTO mode and `/sources/{id}/retry` API allowlist target `status IN ('error','plan_ready')`. New C1 fix initially used `'failed'` (mirrored existing pattern); changed to `'error'` for downstream compatibility.

**Exposure:** Pre-existing LMStudioDownError handler may be invisible to auto-retry workflows. Not in scope for this task, but flagged.

**Lesson:** When extending a state machine, audit which downstream tools read each state value, not just which upstream code writes it. A single typo in an enum can render a recovery flow permanently invisible.

## What's Next (Deferred)

- **M5 probe edge case:** Accept `data:[]` in probes (currently errors on empty page list — triggers on network retry).
- **DRY exception handlers:** Consolidate `LMStudioDownError` pattern in `pipeline.py` (currently duplicated across multiple handlers).
- **Status enum audit:** Rename `pipeline.py` LMStudioDownError handler to use `'error'` instead of `'failed'` to stay compatible with retry-sources.sh allowlist.
