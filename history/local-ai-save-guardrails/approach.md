# Approach

## Mode

Small change.

## Implementation

- Add API validation for nonblank model IDs and valid numeric ranges on Local AI config updates.
- Trim model IDs and host URL in the frontend Save payload.
- Add frontend Save validation so blank/default-prone payloads are rejected before the API call.
- Add min/max attributes to numeric inputs to guide valid values.
- Add tests proving manual model IDs persist when Settings models differ, and malformed payloads are rejected.

## Verification

- `uv run pytest tests/integration/admin/test_local_ai_api.py tests/unit/ai/local_orchestrator/test_config.py -q`
- `uv run ruff check app/routers/admin_local_ai.py tests/integration/admin/test_local_ai_api.py`
- `npm run lint -- 'src/app/(portal)/admin/local-ai/page.tsx' 'src/app/(portal)/admin/local-ai/phase-config-section.tsx'`
- `npx tsc --noEmit --pretty false`
