# Discovery

## Findings

- The backend `POST /api/admin/local-ai/config` correctly persists valid `vision`, `main_llm`, and `embedding` model IDs when it receives them.
- The live config had `settings_models.vision_model_id` differing from `vision.model_id`, so Save must remain separate from Settings sync.
- `_kv_to_config` intentionally falls back to `MAX_PRESET` when stored values are empty. That makes accepting blank model IDs dangerous because a later load can look like a reset to defaults.
- Numeric fields accepted invalid ranges, including the live `ram_headroom_gb = -0.5` value.

## Evidence

- Targeted backend tests passed before changes for valid payload persistence.
- A temporary live API probe saved `probe-vision-model`, `probe-main-model`, and `probe-embedding-model`, verified reload, then restored the original values.
- Frontend App Router guidance was checked from `frontend/node_modules/next/dist/docs/01-app/index.md`.
