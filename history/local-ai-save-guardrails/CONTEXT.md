# Local AI Save Guardrails

## Boundary

Fix the `/admin/local-ai` Save behavior so manual model edits persist predictably and cannot be silently reloaded as preset defaults. Keep Settings model synchronization explicit through the existing `Use Settings Models` action.

## Domains

- SEE: Admin Local AI page fields, Save button, validation messages.
- CALL: `/api/admin/local-ai/config` update contract.
- ORGANIZE: Local AI config values stored under `local_ai.*` keys.

## Locked Decisions

- D1: Manual edits in Local AI model fields must be saved as Local AI config values, even when `/settings` has different active models.
- D2: Copying model IDs from `/settings` remains an explicit sync action and must not happen as a side effect of Save.
- D3: Blank model IDs and invalid numeric tuning values must be rejected before persistence instead of relying on fallback defaults.

## Scout Paths

- `frontend/src/app/(portal)/admin/local-ai/page.tsx`
- `frontend/src/app/(portal)/admin/local-ai/phase-config-section.tsx`
- `app/routers/admin_local_ai.py`
- `app/ai/local_orchestrator/config.py`
- `tests/integration/admin/test_local_ai_api.py`

## Validation Notes

Backend probe against the live API confirmed valid manual model IDs persist and reload correctly. The remaining risk was malformed payloads, especially blank model IDs and invalid numeric values, because config loading falls back to `MAX_PRESET` for empty values.
