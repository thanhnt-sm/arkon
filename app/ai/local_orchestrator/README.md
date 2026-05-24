# local_orchestrator

Manages LM Studio (MLX backend) for the arkon MRP pipeline on M1 Max 32GB.
Controls three co-resident models — vision, main LLM, embedding — via
sequential cold-swap and two user-facing modes: `max` and `other`.

## Module ownership

| File | Owned by |
|------|----------|
| `presets.py` | This module — single source of truth for MAX_PRESET |
| `config.py` | This module — KV schema + load/save |
| `__init__.py` | This module — public exports |
| `alembic/versions/029_seed_local_ai_kv.py` | This module — imports presets directly |

**Do not** edit `presets.py` values without also re-running the migration or
manually updating the `app_config` rows — they share the same constants.

## Integration map

```
app/ai/local_orchestrator/
    ↑ depended by: app/ai/mrp/pipeline.py (Phase 03)
    ↓ depends on:  app/services/config_service.ConfigService
                   app/database/models.AppConfig
```

Phase 02 adds `lms_client.py` (LM Studio SDK wrapper).
Phase 03 adds `phase_router.py` (state machine consumed by `mrp/pipeline.py`).
Phase 04 adds `prompt_templates/` and `sampling_profiles.py`.

## KV key list (`local_ai.*`)

```
local_ai.mode                             "off" | "max" | "other"  (default: off)
local_ai.lms_host                         LM Studio base URL
local_ai.lms_auth_token                   Bearer token (empty = no auth)

local_ai.vision.model_id
local_ai.vision.fallback_model_id
local_ai.vision.context_length
local_ai.vision.eval_batch_size
local_ai.vision.gpu_ratio

local_ai.main_llm.model_id
local_ai.main_llm.fallback_model_id
local_ai.main_llm.context_length
local_ai.main_llm.eval_batch_size
local_ai.main_llm.gpu_ratio
local_ai.main_llm.flash_attention
local_ai.main_llm.kv_cache_offload

local_ai.embedding.model_id
local_ai.embedding.fallback_model_id

local_ai.sampling.<phase>.temperature     phases: refine map verify reduce digest vision
local_ai.sampling.<phase>.top_p
local_ai.sampling.<phase>.top_k           (absent for vision phase)
local_ai.sampling.<phase>.min_p           (absent for vision phase)
local_ai.sampling.refine.repeat_penalty   (refine only)
```

Total: ~40 keys. All seeded by `029_seed_local_ai_kv.py`.

## Mode semantics

| Behaviour | `off` | `max` | `other` |
|-----------|-------|-------|---------|
| LM Studio routing active | No | Yes | Yes |
| Pre-filled model defaults | — | Yes | Yes (same as max) |
| Context length / batch tuning | — | Yes | No |
| Flash attention / KV offload | — | Yes | No |
| Per-phase sampling from KV | — | Yes | Arkon code defaults |
| Vietnamese system prompt | — | Yes | Yes |
| Few-shot prompt scaffolding | — | Yes | No (zero-shot) |

`mode=off` is the install default. The MRP pipeline falls back to the existing
cloud/local provider path when mode is `off`.

## Model verification (required before first `max` run)

1. **Vision** — `mlx-community/Qwen2.5-VL-32B-Instruct-4bit`
   Confirm repo exists on HuggingFace before enabling max mode.

2. **Main LLM** — `mlx-community/Qwen3.6-35B-A3B-4bit-DWQ`
   **UNVERIFIED** — repo name may differ. If missing, update
   `local_ai.main_llm.model_id` in admin UI to the confirmed fallback:
   `mlx-community/Qwen3-32B-Instruct-4bit`

3. **Embedding** — `Alibaba-NLP/gte-Qwen2-1.5B-instruct`
   Loaded via `sentence-transformers` (MPS), not through LM Studio.

## K/V cache quantization (manual step)

LM Studio SDK v1.5 does not expose K/V cache quantization programmatically.
Set `q8_0` manually in **LM Studio UI → Model Settings → KV Cache Quantization**
for both vision and main_llm models before running max mode.

## RAM budget (M1 Max 32GB)

| Phase | Models active | Peak RAM |
|-------|--------------|----------|
| Vision | Qwen2.5-VL-32B 4-bit | ~31 GB |
| Main LLM | Qwen3.6-35B-A3B + embedding on-demand | ~31–32 GB |
| Idle | None loaded | ~11 GB |

Both active phases are borderline. Phase 06 adds pre-flight RAM checks and
auto-fallback to smaller models on consecutive OOM.
