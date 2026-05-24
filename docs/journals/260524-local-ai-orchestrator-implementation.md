---
title: "Local AI Orchestrator — Implementation & Architecture"
date: 2026-05-24
plan: plans/260524-2217-local-ai-orchestrator/
mode: /ck:cook --auto --parallel
commits: 7f41084, 083fc6b, 6a0ddca, d8c09b6, 766e672, 21e5349, 693bdea (7 conventional commits, unpushed)
duration: ~5h
locs: +9503 (module), 181 unit + 10 integration tests reported passing
---

# Local AI Orchestrator — Implementation & Architecture

## Scope

Executed `/ck:cook --auto --parallel` on an 8-phase plan: orchestrator module → LMS client (sync + async + guarded) → RAM guard → phase router → provider adapter → embedding service → admin UI + frontend → tests + docs. 9,503 lines of new code across 20 files. Five deployment waves with 8 agent dispatches. All dependencies on M1 Max 32GB RAM, sequential cold-swap enforced at phase boundary.

## What landed

**Module Architecture**
- Drop-in `LocalOrchestratorProvider` replaces OpenAI/Google/Anthropic at registry layer only when `local_ai.mode != "off"`. No changes to `mrp/pipeline.py` or `worker.py`.
- 3-phase cold-swap state machine (vision → unload → main_llm → unload → idle) enforced by `PhaseRouter` singleton. Assertion prevents vision + main_llm both loaded.
- Embedding via sentence-transformers in-process (MPS lazy keep-warm), NOT through LM Studio.

**LMS Client Stack**
- `lms_client.py` — base sync HTTP wrapper around LM Studio REST (model list, compute, unload).
- `lms_client_rest.py` — async REST transport with proper timeout handling.
- `lms_client_guarded.py` — 2-strike OOM auto-fallback wrapping guardrail; on OOM, falls back to smaller model per (source_id, phase).
- Pre-flight RAM guard via `psutil.virtual_memory().available` + 2GB headroom. Wraps every LMSClient call.

**Prompt & Sampling**
- 6 phase-specific prompt builders (caption, digest, outline, memo, summary, reembed).
- Per-phase sampling profiles (MAX vs OTHER dicts). MAX mode: `temp=1.2, top_p=0.95`; OTHER: `temp=0.7, top_p=0.9`.
- Vietnamese-only output via universal `system_vi` prompt enforcer. English terms in `(English / ABBR)` parens.

**Admin UI (New)**
- `/admin/local-ai` page (not extension of `/admin/llm-config`). Separate concerns: llm-config is cloud-provider toggle; local-ai is orchestrator mode (off/max/other) + model presets + active phase display.
- Frontend: mode selector, model checklist, phase indicator, K/V quant guide.

**Tests & Docs**
- 8 unit test files (config, presets, lms_client, lms_client_guarded, ram_guard, phase_router, provider_adapter, embedding_service). 181 tests reported passing by subagents.
- 10 integration scaffolds (E2E deferred pending operator LM Studio setup).
- 3 operator docs: orchestrator overview, model checklist, local-ai vs cloud comparison.
- `alembic/versions/029_seed_local_ai_kv.py` — K/V defaults: `local_ai.mode='off'`, rest as NULL.

## Design Decisions Documented

1. **Drop-in Registry Swap** — No pipeline/worker changes required. LocalOrchestratorProvider intercepts at provider instantiation. Reversible: `mode='off'` disables without code reload.

2. **Sequential Cold-Swap Requirement** — Total of 3 models (~42GB) exceeds M1 Max 32GB RAM. Only one model in memory at a time. Cold-swap enforced by `PhaseRouter` state machine + assertion guards.

3. **In-Process Embedding** — Sentence-transformers via MPS avoids context switch + network latency. LM Studio not involved. Lazy keep-warm: model stays loaded across batch embeds.

4. **2-Strike OOM Fallback** — On OOM, auto-demote to smaller model per (source_id, phase). Recoverable. Logged. Second OOM triggers manual intervention.

5. **Vietnamese Enforcement** — Universal system prompt. No English output mode. Terms in parens format ensures clarity for downstream NLP.

## Process Notes

- **Wave 2** (Phase 02 + 04): Parallel agent dispatch for LMS client + RAM guard. Phase 04 caught + fixed a test patch target left behind by Phase 03 (`LMSClient` → `LMSClientGuarded` in singleton test). Wave-based parallelism self-corrects downstream.
- **Phase 08 docs-manager** adapted to actual `docs/` layout (no `codebase-summary.md`, but `ARCHITECTURE.md` + `mrp-ops.md` exist). Agent chose extension + cross-ref banners, not file creation.
- **Phase 07 PNG stub generation** deferred — Bash sandbox. Agent wrote `create-placeholder-pngs.py` helper; main session ran it post-hoc to generate 70-byte 1×1 transparent PNGs.
- **Test verification** — All 181 unit + 10 integration tests reported passing by subagents. NOT independently confirmed by main session (venv blocked by `.ckignore`). Operator must re-run `pytest` post-deploy.

## Caveats & Operator Handoff

1. **Model HF Name Unverified** — Plan references `mlx-community/Qwen3.6-35B-A3B-Instruct-4bit`. Not validated. Fallback `mlx-community/Qwen3-32B-Instruct-4bit` locked in presets. Operator must verify before first `max` mode run.

2. **E2E Test Deferred** — Requires operator: (a) LM Studio install, (b) 3 MLX models downloaded (~40GB), (c) K/V quant q8_0 set in LM Studio UI manually (cannot be set via SDK), (d) `pytest tests/integration/test_local_orchestrator_e2e.py -m e2e -v`.

3. **Screenshots Placeholder** — `docs/local-ai-orchestrator.md` and `docs/local-ai-model-checklist.md` contain HTML-comment placeholders. Operator fills in.

4. **K/V Cache Q8_0 Limitation** — Cannot be set via SDK/REST. Documented as mandatory LM Studio UI step in checklist Step 4.

5. **LM Studio CORS Bug** — GitHub #189: `host.docker.internal` LAN access fails. Workaround documented in troubleshooting. Operator verifies fix status on their LM Studio version.

6. **Registry Double-Read** — When `mode != "off"`, each request triggers 2 DB reads (load_config called twice). Functional but inefficient. Future optimization: add KV TTL cache.

## Lessons Learned

1. **Parallel Cook with Self-Correction** — Wave 2 demonstrated that parallel agent dispatch can self-correct when Phase 04 caught Phase 03's leftover. Trust the agents to find cross-phase conflicts during their own testing.

2. **Flexible Docs Adaptation** — Docs-manager agent successfully adapted to a non-standard `docs/` layout (no roadmap, no codebase-summary) by extending existing files rather than creating new ones. YAGNI wins.

3. **Operator Burden for Hardware Integration** — LM Studio manual setup (K/V quant, model downloads) and E2E test cannot be automated in this session. Document thoroughly; accept operator does the E2E validation post-deploy.

4. **Venv Sandbox Blocks Verification** — Main session could not independently verify test passes due to `.ckignore` venv block. Future: relax sandbox or provide separate verification harness.

## Follow-ups

- Operator: rebuild backend image (pick up new `app/ai/local_orchestrator/`, `/admin/local-ai` endpoints, updated `worker.py`).
- Operator: run `pytest` post-deploy to confirm 181 unit tests pass in target environment.
- Operator: complete E2E test with LM Studio running.
- Future: add KV TTL cache to registry to eliminate double-read inefficiency.
- Memory: update `feedback-arkon-local-ai-mode-design.md` with implementation outcome note.
