---
title: "Fork Protection — Ours-First Upstream Conflict Policy"
date: 2026-05-24
commit: e882ca6 (feat(mrp): LLM pre-flight ping + abort-early retry + caption sanitization)
upstream: github.com/nduckmink/arkon (read-only reference)
origin: github.com/thanhnt-sm/arkon (production)
---

# Fork Protection — Ours-First on Upstream Sync

## Context

Origin is now ahead of upstream by an accumulating set of hardening commits (MRP resilience, LLM pre-flight, VLM caption defense, sequential writer, stub breaker, LAN squid policy). The user requested that every future `/ck:sync-audit-upstream` cycle defaults to **ours-first** on conflict.

## Decision

On any conflict between `upstream/main` and `origin/main`:

1. **Default action = keep ours.** Upstream hunks are accepted only when they are:
   - Pure-additive (new files / new symbols that don't shadow existing local logic), OR
   - A scoped bug fix with a clear CVE / issue reference, AND
   - Verified not to regress any item in the divergence catalog.

2. **Files in the divergence catalog are non-negotiable.** Anything touching `app/utils/caption_sanitize.py`, `app/utils/text.py::parse_json_loose`, `app/ai/mrp/{mapper,reducer,writer}.py`, `app/worker.py` (pre-flight ping + caption sanitize + intake-paused hooks), `squid/squid.conf`, `app/llm/*` profile toggle, `scripts/retry-sources.sh`, `scripts/regen-wiki.sh`, `.claude/skills/sync-audit-upstream/`, `docs/journals/*` → recategorize as `keep-local` even if `categorize_conflicts.sh` says otherwise.

3. **Smoke test required after every sync:**
   - `uv sync` clean.
   - `pytest tests/test_text_parse_json.py tests/test_mrp_*.py` green.
   - Manual: LLM-down pre-flight raises within 60s.
   - Manual: VLM refusal collapses to `""` not raw string.

4. **Audit trail:** every accepted upstream hunk recorded in `.agent/sync_history/` with one-line reason.

## Why

The fork is the production deployment. Upstream is a research/dev tree without the resilience layers we've shipped. Losing `MIN_FIRST_ROUND_SUCCESS_RATE` alone costs ~21 minutes per failed run when LM Studio is wedged. Losing `caption_sanitize` pollutes `source.full_text` with hallucination loops and refusal strings, contaminating downstream MRP. The cost of an over-cautious sync (a few additional `keep-local` flags) is far less than re-deriving these fixes from incident logs.

## What changed in this commit batch (e882ca6)

| File | Change | Why |
|------|--------|-----|
| `app/worker.py` | 60s LLM pre-flight ping | Surface dead LM Studio before ~21min MAP timeout burn |
| `app/worker.py` | `_sanitize_caption` on every caption write | Stop VLM hallucination loops from reaching DB |
| `app/ai/mrp/mapper.py` | `MIN_FIRST_ROUND_SUCCESS_RATE=0.30` abort guard | Skip sequential retry when LLM clearly down |
| `app/ai/mrp/reducer.py` | Module-scope settings import | Remove 3× lazy imports from hot path |
| `app/utils/text.py` | Quote unquoted JSON property names | Fix gemma family drift into Python-dict syntax |
| `app/utils/caption_sanitize.py` (new) | Refusal / hallucination / CJK-leak defense | Defensive layer below VLM outputs |
| `uv.lock` | Sync | Required by `uv sync` |

## Persistence

- Memory (auto-recalled across sessions):
  - `feedback-arkon-upstream-conflict-policy.md` — the rule itself.
  - `project-arkon-fork-divergence.md` — the running catalog of protected files.
- Skill reference:
  - `.claude/skills/sync-audit-upstream/references/conflict-resolution-guide.md` — appended "Ours-First Default for Arkon Fork" section so any subagent reading the skill inherits the policy.

## Follow-ups

- After next upstream sync, append entry to `.agent/sync_history/` even if no merge occurred (record fetch-only audits too).
- Re-evaluate ours-first stance if upstream ever lands its own pre-flight/abort-early logic — then merge becomes a careful integration, not a discard.
