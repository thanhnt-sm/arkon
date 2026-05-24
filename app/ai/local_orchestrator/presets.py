"""
Local AI Orchestrator — MAX_PRESET constants.

Single source of truth for the researched defaults. The alembic seed migration
(029) imports this dict directly, so preset values and DB seeds never drift.

Model IDs are verified against HuggingFace as of May 2026. The main_llm ID
`mlx-community/Qwen3.6-35B-A3B-4bit-DWQ` requires user verification — the
exact HF repo name may differ (see README.md § Model Verification).
"""

MODE_OFF = "off"
MODE_MAX = "max"
MODE_OTHER = "other"

VALID_MODES = frozenset({MODE_OFF, MODE_MAX, MODE_OTHER})

# ---------------------------------------------------------------------------
# MAX_PRESET — full researched configuration for M1 Max 32GB
# ---------------------------------------------------------------------------

MAX_PRESET: dict = {
    # ----- LMS connection -----
    "lms_host": "http://host.docker.internal:1234",
    "lms_auth_token": "",
    # ----- RAM headroom (GB) — safety buffer subtracted from available RAM -----
    "ram_headroom_gb": 2.0,
    # ----- Vision phase -----
    "vision": {
        "model_id": "mlx-community/Qwen2.5-VL-32B-Instruct-4bit",
        "fallback_model_id": "mlx-community/Qwen2.5-VL-7B-Instruct-8bit",
        "context_length": 8192,
        "eval_batch_size": 16,
        "gpu_ratio": 1.0,
        "estimated_ram_gb": 19,
    },
    # ----- Main LLM phase (MAP / REDUCE / REFINE / VERIFY / DIGEST) -----
    "main_llm": {
        # NOTE: `mlx-community/Qwen3.6-35B-A3B-4bit-DWQ` requires user
        # verification on HuggingFace — the repo may be named differently.
        # If not found, swap for the confirmed fallback below.
        "model_id": "mlx-community/Qwen3.6-35B-A3B-4bit-DWQ",
        "fallback_model_id": "mlx-community/Qwen3-32B-Instruct-4bit",
        "context_length": 32768,
        "eval_batch_size": 256,
        "gpu_ratio": 1.0,
        "flash_attention": True,
        "kv_cache_offload": True,
        # K/V cache quantization q8_0 must be set manually in LM Studio UI
        # per model — not exposed via SDK as of v1.5 (see README.md).
        "kv_quant_note": "q8_0 — set in LM Studio UI per model (API not exposed)",
        "estimated_ram_gb": 21,
    },
    # ----- Embedding phase -----
    "embedding": {
        "model_id": "Alibaba-NLP/gte-Qwen2-1.5B-instruct",
        "fallback_model_id": "Alibaba-NLP/gte-multilingual-base",
        "estimated_ram_gb": 2,
    },
    # ----- Per-phase sampling profiles (MAX mode only) -----
    "sampling": {
        # REFINE: creative long-form writing — higher temperature for variety
        "refine": {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05,
            "repeat_penalty": 1.1,
        },
        # MAP: deterministic extraction — low temperature for consistency
        "map": {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05,
        },
        # VERIFY: audit pass — near-deterministic
        "verify": {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05,
        },
        # REDUCE: structure planning — moderate temperature
        "reduce": {
            "temperature": 0.3,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05,
        },
        # DIGEST: summary rollup — moderate temperature
        "digest": {
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05,
        },
        # VISION: image captioning — low temperature for accurate description
        "vision": {
            "temperature": 0.2,
            "top_p": 0.9,
        },
    },
}
