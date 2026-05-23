---
title: Sync-Audit Skill Hardening — Phases 1-3
date: 2026-05-23
author: thannt
related_plan: plans/260523-1412-sync-audit-skill-hardening/
commits: [ee017b4, 3aad17d, 1e72bb9]
---

# Sync-Audit Skill Hardening

Three phases delivered in one session. Shipped 33/33 tests green across 4 suites; baseline audit has 0 false positives.

## What shipped

**Phase 1 — Critical bug fixes + hard gate.** `run_audit.sh` rewritten end-to-end with strict env/JSON/YAML parsing instead of free-form `grep -r`. The skill's own docs no longer match its own forbidden-SDK patterns. `safe_sync.sh --merge` is now a shell-enforced gate: refuses unless a report with frontmatter `upstream_sha: <full-sha>` + `audit_status: PASS` exists. `watch_sync.sh` upgraded (per direction, not deleted) — cross-platform fswatch/inotifywait, PID lock, debounce, `--once` mode.

**Phase 2 — Deterministic conflict pipeline + PII Check #10.** Replaced LLM-judgment conflict categorization with `categorize_conflicts.sh` (JSON/CSV/summary output, 10-run hash-stable). `preview_merge.sh` materializes the merge on a disposable branch — review with `git diff <current>...merge-preview-<ts>`. `sync_rollback.sh` has 3 modes (last-merge revert / patch reverse-apply / hard reset with typed-yes confirmation). Check #10 layers network-entrypoint + PII-keyword + non-allowlisted-host to flag exfiltration.

**Phase 3 — CI + observability.** GitHub Action runs the same pipeline weekly (Monday 01:00 UTC) plus manual `workflow_dispatch`. Opens an idempotent issue per upstream SHA on WARN/FAIL. Three helper scripts (`generate_report.sh`, `update_metrics.sh`, `append_index.sh`) anchor on `git rev-parse --show-toplevel` so they work in the real workspace, in CI clones, and in ephemeral test repos.

## Key decisions

- **AI whitelist expanded** to Mistral, Cohere, Groq, OAuth2 (in addition to OpenAI/Anthropic/Google Gemini). Single source of truth: `ALLOWED_AI_HOSTS` in `audit-helpers.sh` — both Check #3 network scan and Check #10 PII scan import it. `squid/squid.conf` mirrors the list verbatim.
- **`MIN_SEMANTIC_LOC = 5`, fixed** (KISS). Adaptive-per-file-size proposals deferred; the casual threat model doesn't need it.
- **Force-push: warn-only**, never block. Logged to `.agent/sync_history/force-push.log` for forensic recovery.
- **`watch_sync.sh` upgraded, not deleted.** Original "should we delete?" question reframed when user wanted maximum value.
- **Stateful services without `read_only: true`** are INFO not WARN — databases legitimately need writes. Hardening WARN was noise for our compose layout.

## Lessons

- **macOS bash is 3.2.** No `declare -A`. Switched all test runners to parallel-index arrays. Production scripts already used indexed arrays, so the hit was contained to test infrastructure.
- **`set -euo pipefail` + glob + grep is a landmine.** When `plans/reports/sync-audit-*.md` doesn't expand (no match), bash passes the literal pattern to grep, grep exits 2 ("file not found"), pipefail makes the pipeline non-zero, set -e kills the script before the `[ -z "$REPORT" ]` check. Fix: `shopt -s nullglob` + array materialization + `|| true` on the grep pipe. Cost an hour of head-scratching during test 1 of the gate suite.
- **Don't write log files inside the working tree of a script that calls `git switch`.** `preview_merge.sh` originally wrote its log to `.agent/sync_history/` (committed it via `git add -A`), then redirected the final `git switch` output back into the same file → unstaged modification → git refused the switch with "Your local changes would be overwritten." Moved logs to `$TMPDIR/arkon-sync-history/`. Trivial in retrospect, opaque in the moment.
- **Scripts that touch repo state should anchor on `git rev-parse --show-toplevel`**, not on `dirname "${BASH_SOURCE[0]}"`. The latter pins to the script's installed location; the former pins to the repo being acted on. Mattered for test isolation (ephemeral repos in `$TMPDIR`) and would matter equally if a script ever moved.
- **Determinism testing is cheap and high-signal.** The 10-run sha256 stability check on `categorize_conflicts.sh` is 5 lines and catches non-deterministic orderings (e.g. unsorted `find` output) immediately. Worth adding to anything that claims to be deterministic.
- **Issue-creation idempotency by short SHA literal** in the workflow grep — not by title equality — survives title-format edits without spamming. Slight foot-gun: if the title is ever changed to omit the SHA, dedup breaks silently.

## Known limitations (acceptable for casual threat model)

- LOC counter doesn't parse block comments — multi-line `/* ... */` inner lines count as changes unless they start with `*`. Phase 4 (deferred) would use AST parsing.
- File-rename detection not implemented (`git diff --find-renames`). Renames surface as `upstream-deleted` + new file. Could mis-categorize a rename-with-edits as security-risk loss.
- `update_metrics.sh` falls back to no-op locking when `flock` isn't installed (default on macOS). Single-writer assumption holds in practice — interactive runs never overlap — but isn't guaranteed under CI + git-hook concurrency.
- Reports + plans + skills are intentionally gitignored. Functional changes ship; documentation context lives locally. Tradeoff: onboarding new contributors requires re-running the skill to regenerate references.

## What's next

- **Dogfood weeks 1-2:** let the GitHub Action run twice, observe the issue stream, verify dedup. Tune `MIN_SEMANTIC_LOC` only if surfacing pain.
- **Deferred:** Phase 4 Python rewrite + AST-based LOC + Socket.dev/Snyk integration + sandbox `--ignore-scripts` enforcement + upstream commit signature verification. All gated on threat model rising from "casual upstream cẩu thả" to "targeted."

## Pointers

- Plan: `plans/260523-1412-sync-audit-skill-hardening/`
- Scripts: `.agent/workflows/`
- Tests: `.agent/workflows/test/run-*.sh`
- CI: `.github/workflows/upstream-audit.yml`
- Skill docs (local-only): `.claude/skills/sync-audit-upstream/`
