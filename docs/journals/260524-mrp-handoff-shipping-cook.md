---
title: "MRP Handoff Shipping — Cook Execution"
date: 2026-05-24
plan: plans/260524-0230-mrp-handoff-shipping/
mode: /ck:cook --auto
commits: 59ab366..c149b68 (13 conventional commits, unpushed)
duration: ~2h
---

# MRP Handoff Shipping — Cook Execution

## Scope

Executed `/ck:cook --auto` on the 4-phase plan: hot-patches → unit tests → migration+smoke → frontend+docs+commit. 13 conventional commits landed on `main` locally; push intentionally deferred.

## What landed

**Phase 01 — Hot Patches (30m)**
- F1: `source.metadata_` JSONB write at `app/ai/mrp/pipeline.py:587-602` (was silent no-op on `metadata_json` attr name mismatch). Now writes `digest_failed`, `digest_error`, `digest_failed_at` via the real `metadata_` attr (DB column `"metadata"`).
- F2: `.gitignore` now excludes `logs/`, `*.log`, `*.egg-info/`.
- F3: `scripts/ab-validate-mrp-v2.sh` invokes `python3 scripts/regen-failed-source.py` directly (Python forbids dashes in module names). Docstring in `regen-failed-source.py` corrected to match.

**Phase 02 — Unit Tests (1.80s)**
- 59/59 tests pass (3 files, parametrized).
- Cloud-config regression test asserts exact pre-change constants: `concurrency=6, chunk_chars=20_000, extract_timeout_s=120, retry_attempts=3`. Catches accidental edits to the cloud branch of `derive()`.
- Local-profile thresholds verified across 8 cases (8k/16k/32k boundaries).
- LADDER allowlist verified across 17 cases including literal hosts, RFC1918 CIDRs, and cloud markers.
- `classify_pipeline_shape` boundaries verified at `STUFF_THRESHOLD_CHARS=8_000`, `SINGLE_MAP_THRESHOLD_CHARS=20_000`, and 500_000.
- Wiki-link allowlist rejects `[[../etc/passwd]]` and unauthorized slugs; preserves pipe-aliased valid links.

**Phase 03 — Migration + Smoke (partial)**
- Alembic migration `028_seed_llm_profile_kv.py` applied to dev DB via direct SQL (container image predates the new revision; applied via `psql -f` then stamped `alembic_version='028'`).
- 4 KV rows seeded: `llm_profile='local'`, `llm_context_length=NULL`, `llm_model_name=NULL`, `mrp.intake_paused='false'`.
- F1 JSONB write schema validated end-to-end via synthetic insert + rollback on a real source row.
- **Skipped**: A/B harness (only 1 source in `error` state — DELETE-regen too risky in `--auto`) and `/api/llm-health` smoke (container image predates the new endpoint — needs rebuild post-deploy).
- **Open Question #4 resolved**: `runtime_profile._PROFILE_CACHE` is module-scope with 60s TTL. `alembic downgrade -1` removes the KV rows but worker processes serve the cached profile for up to 60s. Operator fix: restart worker container after downgrade, or call `PATCH /api/app-config` to trigger `invalidate()`. Documented in `docs/mrp-ops.md` + `docs/local-llm.md`.

**Phase 04 — Frontend + Docs + Commit Split**
- Frontend `digest` page-type added to `WikiPageType` union, `WikiTypeBadge` map, and `wikiTypeGroupLabel`. Inline badge "AI-generated summary" with `auto_awesome` icon injected into wiki page renderer when `page.page_type === 'digest'`.
- Frontend type-check clean. Lint surface unchanged (pre-existing `canReview` unused-var + setState-in-effect were already there — not in scope).
- 13 conventional commits in topical order: runtime_profile → MRP pipeline → provider retry → admin endpoints → sources regen → wiki service → worker pause → migration+squid (release-note in body) → scripts → frontend badge → docs (mrp-ops/local-llm/ARCHITECTURE/journal) → gitignore+tests → docs follow-up (WIKI/HOW_TO_RUN/ARCHITECTURE header).
- Release-note warning embedded in commit 8 (`3bf46ec`) body for cloud-install behavior and rollback cache gotcha.

## What didn't land

- `git push origin main` — held for user verification. 13 direct-to-main commits is irreversible; the plan acknowledged the audit-trail compromise.
- A/B harness run on 3 sources of different sizes (no candidates available in dev DB).
- Live `/api/llm-health` smoke (container image lag).
- `uv.lock` — session artifact, untracked; user decides whether to commit.

## Hand-offs

- **Operator (post-push)**: rebuild backend image so the running container picks up `app/ai/runtime_profile.py`, the new `/api/llm-health` + `PATCH /api/app-config` endpoints, and the `mrp.intake_paused` worker gate. Migration is already applied — no re-run needed.
- **Operator (48h monitoring)**: watch `/api/llm-health` profile flag; should not flip unintentionally. Documented as out-of-scope for this cook.
- **Follow-up plan candidate**: deferred parent-plan phases 05/06/07 (chunked digest streaming, multi-source merge, batch reembed). Decision needed: file as new plan or close as v2-scope.

## Notes for next session

- `uv sync` stalled on torch-class downloads (>4 min no progress, low CPU). Workaround that worked: `uv pip install pytest pytest-asyncio loguru sqlalchemy pydantic` — keeps the existing venv, installs only the test deps. Faster than waiting for full `uv sync` on cold cache.
- The arkon_api / arkon_worker container images are read-only and predate the post-026 migrations + endpoints. To run new code in dev, rebuild the image (`docker compose build api worker` then `up -d`) rather than trying to copy files in.
- Plan referenced `docs/code-standards.md`, `docs/development-roadmap.md`, `docs/project-changelog.md` — none exist. Per YAGNI we did not create them; the relevant content landed in existing `docs/ARCHITECTURE.md`, `docs/mrp-ops.md`, and `docs/local-llm.md`.
