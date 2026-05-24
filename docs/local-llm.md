# Local-LLM Operator Note

Quick reference for running arkon's MRP pipeline against a local LM Studio
(profile=local) vs a cloud OpenAI-compatible endpoint (profile=cloud).

**New:** For comprehensive local AI setup (model download, LM Studio config, K/V quantization, migration), see [Local AI Orchestrator](./local-ai-orchestrator.md) and [Model Checklist](./local-ai-model-checklist.md). This page covers legacy profile toggling.

## Toggle profile

- SQL: `psql -c "UPDATE app_config SET value='cloud' WHERE key='llm_profile';"`
- API: `PATCH /api/app-config` body `{"updates":{"llm_profile":"cloud"}}` (admin only)

Cache invalidates immediately; next ingest picks up the new profile.

## Inspect runtime config

- Logs: `docker logs arkon_worker 2>&1 | grep '\[profile='`
- Endpoint: `GET /api/llm-health` returns `{profile, context_length, model_name, last_probe_ok, last_probe_ts, intake_paused}`.

## Pause intake (for A/B harness)

`scripts/ab-validate-mrp-v2.sh <uuid> ...` flips `mrp.intake_paused=true`,
DELETE-regens pages, restores the flag on EXIT. Workers re-enqueue with `_defer_by=60`.

## Manual digest regen

`POST /sources/{id}/regen-digest` (admin only, 1/min/source rate limit).

## Revert

`alembic downgrade -1` removes only the seed KV rows for `llm_profile`,
`llm_context_length`, `llm_model_name`, `mrp.intake_paused`. No schema change to undo.

**Important**: the `runtime_profile` module-scope cache survives the downgrade
for up to 60s (TTL). To force a fresh probe on rollback, restart the worker
container — see `docs/mrp-ops.md` → "Rollback gotcha — runtime_profile cache TTL".

## Cloud install warning

The migration auto-detects cloud profile via the `llm_base_url` host
(openai.com, anthropic.com, togetherapi.com, groq.com → `cloud`). If your
host doesn't match, run the SQL UPDATE above immediately after upgrading.
