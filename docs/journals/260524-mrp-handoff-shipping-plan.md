# MRP Handoff Shipping: Plan + Bug Discovery Session

**Date**: 2026-05-24 02:53  
**Severity**: High  
**Component**: MRP pipeline (cook handoff into ship phase)  
**Status**: Planned, 3 bugs discovered, Phase 1 ready for cook

## What Happened

Received cook handoff (7/10 phases complete, 11 modified + 7 untracked files on main, no smoke run). Brainstorm+planning session uncovered **3 NEW bugs not in original handoff** and drafted 4-phase shipping plan with deliberate risk trade-offs.

## The Brutal Truth

We shipped the MRP overhaul cook without running smoke tests. That's reckless, but we caught critical failures in planning that would've blown up production. The pipeline is fragile — metadata column mismatch, broken Python module names, logs polluting git. If we'd merged without this session, the operator would inherit a silent no-op failure that corrupts wiki page batches.

## Technical Details

**F1: Metadata Column Mismatch (CRITICAL)**
- Pipeline digest-failure write silently fails: `Source.metadata_` ≠ `metadata_json`
- Root: Model definition at `app/database/models.py:141` never synced with alembic migration
- Impact: Wiki regen batches marked "complete" but metadata never written; causes cascading failures on retry
- Fix: Single-line model patch + data cleanup step in Phase 3 migration

**F2: Logs Gitignore Incomplete**
- `logs/` (668KB) contains operator run logs, not tracked in `.gitignore`
- Current: only `logs.txt` + `claude/hooks/.logs/` covered
- Impact: Commit bloat, accidental credential leak risk if operator logs contain API keys
- Fix: Add `logs/` to root `.gitignore`

**F3: Python Module Naming Violation**
- A/B harness invokes `python3 -m scripts.regen-failed-source` (dashes forbidden in module names)
- Should be `scripts/regen_failed_source.py` or restructure as `scripts.regen.failed_source`
- Impact: smoke + A/B tests will fail immediately
- Fix: Rename script + update harness references

## What We Tried

Original plan was Option C (hot-patches only, skip tests). User rejected as insufficient; negotiated **Option C+A+B combined** (hot-patches + unit tests + smoke before merge). This adds ~4 hours but gates false confidence.

Pushed for feature-branch+PR workflow; user chose commit-to-main deliberate audit-trail compromise (all changes documented in commit body with reasoning).

## Root Cause Analysis

Cook phase lacked smoke gate. These bugs are implementation errors (model sync oversight, naming carelessness, gitignore scope creep) that should've been caught by basic smoke. We prioritized speed over validation. F1 is the most dangerous — silent failure on success path.

## Lessons Learned

1. **Smoke is not optional on schema changes.** Alembic + model sync are sources of hidden failures; test framework must validate both.
2. **Pre-merge gate uncovers surprises.** These 3 bugs were hiding in plain sight for 2+ days. Brainstorm+plan iteration found them; cook isolation didn't.
3. **Commit message as audit trail works.** Documenting trade-offs (Option C→C+A+B, commit-to-main rationale) in commit body creates defensible record if things break post-deploy.

## Next Steps

**Phase 1 (Hot-patches)**: Apply F1, F2, F3 fixes.  
**Phase 2 (Unit Tests)**: Test derive, classify_pipeline_shape, _enforce_size_cap (3 required gates).  
**Phase 3 (Smoke + Migration)**: Run alembic migration + smoke; investigate cache invalidation on downgrade (Step 3.8).  
**Phase 4 (Frontend + Docs + Commit)**: Merge digest badge UI, update release notes, commit to main.

4 cook tasks hydrated in `plans/260524-0230-mrp-handoff-shipping/`.

## Unresolved Questions

1. **Cache invalidation completeness on alembic downgrade** — Is in-memory cache cleared when migration rolls back? Investigate Phase 3 Step 3.8.
2. **Post-deploy monitoring handoff** — Operator stays on call for 48h; success criteria and escalation path TBD. Who owns handoff debrief?
3. **Deferred phases (05/06/07)** — Profile tuning, rate-limit expansion, async job queue tracked as separate v2 issue. Confirm scope lock with lead.

**Reports**: Brainstorm at `plans/reports/brainstorm-260524-0230-mrp-handoff-shipping.md` | Parent cook at `plans/reports/cook-260524-0205-local-llm-mrp-overhaul.md`
