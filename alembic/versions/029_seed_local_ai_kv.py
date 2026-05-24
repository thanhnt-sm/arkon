"""Seed local_ai.* KV rows (Phase 1, Local AI Orchestrator)

Revision ID: 029
Revises: 028
Create Date: 2026-05-26 00:00:00.000000

Inserts all `local_ai.*` configuration keys into the existing `app_config`
table with MAX_PRESET defaults.  `local_ai.mode` defaults to `'off'` so the
feature is disabled on first deploy — admin must explicitly enable.

NO schema change — AppConfig is `(key PK, value Text, updated_at)`.
Down migration removes only the rows this migration inserted.

Source of truth for values: `app/ai/local_orchestrator/presets.py::MAX_PRESET`.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Import preset values so migration and runtime schema never drift.
# The import resolves at migration-run time (alembic env has app on PYTHONPATH).
from app.ai.local_orchestrator.presets import MAX_PRESET  # noqa: E402

_VISION = MAX_PRESET["vision"]
_MAIN = MAX_PRESET["main_llm"]
_EMBED = MAX_PRESET["embedding"]
_SAMPLING = MAX_PRESET["sampling"]

_SEED_ROWS: list[tuple[str, str]] = [
    # --- Mode selector (default off — feature is opt-in) ---
    ("local_ai.mode", "off"),
    ("local_ai.lms_host", MAX_PRESET["lms_host"]),
    ("local_ai.lms_auth_token", MAX_PRESET["lms_auth_token"]),
    # --- RAM headroom ---
    ("local_ai.ram_headroom_gb", str(MAX_PRESET["ram_headroom_gb"])),
    # --- Vision ---
    ("local_ai.vision.model_id", _VISION["model_id"]),
    ("local_ai.vision.fallback_model_id", _VISION["fallback_model_id"]),
    ("local_ai.vision.estimated_ram_gb", str(_VISION["estimated_ram_gb"])),
    ("local_ai.vision.context_length", str(_VISION["context_length"])),
    ("local_ai.vision.eval_batch_size", str(_VISION["eval_batch_size"])),
    ("local_ai.vision.gpu_ratio", str(_VISION["gpu_ratio"])),
    # --- Main LLM ---
    ("local_ai.main_llm.model_id", _MAIN["model_id"]),
    ("local_ai.main_llm.fallback_model_id", _MAIN["fallback_model_id"]),
    ("local_ai.main_llm.estimated_ram_gb", str(_MAIN["estimated_ram_gb"])),
    ("local_ai.main_llm.context_length", str(_MAIN["context_length"])),
    ("local_ai.main_llm.eval_batch_size", str(_MAIN["eval_batch_size"])),
    ("local_ai.main_llm.gpu_ratio", str(_MAIN["gpu_ratio"])),
    ("local_ai.main_llm.flash_attention", str(_MAIN["flash_attention"]).lower()),
    ("local_ai.main_llm.kv_cache_offload", str(_MAIN["kv_cache_offload"]).lower()),
    # --- Embedding ---
    ("local_ai.embedding.model_id", _EMBED["model_id"]),
    ("local_ai.embedding.fallback_model_id", _EMBED["fallback_model_id"]),
    ("local_ai.embedding.estimated_ram_gb", str(_EMBED["estimated_ram_gb"])),
    # --- Sampling: refine ---
    ("local_ai.sampling.refine.temperature", str(_SAMPLING["refine"]["temperature"])),
    ("local_ai.sampling.refine.top_p", str(_SAMPLING["refine"]["top_p"])),
    ("local_ai.sampling.refine.top_k", str(_SAMPLING["refine"]["top_k"])),
    ("local_ai.sampling.refine.min_p", str(_SAMPLING["refine"]["min_p"])),
    ("local_ai.sampling.refine.repeat_penalty", str(_SAMPLING["refine"]["repeat_penalty"])),
    # --- Sampling: map ---
    ("local_ai.sampling.map.temperature", str(_SAMPLING["map"]["temperature"])),
    ("local_ai.sampling.map.top_p", str(_SAMPLING["map"]["top_p"])),
    ("local_ai.sampling.map.top_k", str(_SAMPLING["map"]["top_k"])),
    ("local_ai.sampling.map.min_p", str(_SAMPLING["map"]["min_p"])),
    # --- Sampling: verify ---
    ("local_ai.sampling.verify.temperature", str(_SAMPLING["verify"]["temperature"])),
    ("local_ai.sampling.verify.top_p", str(_SAMPLING["verify"]["top_p"])),
    ("local_ai.sampling.verify.top_k", str(_SAMPLING["verify"]["top_k"])),
    ("local_ai.sampling.verify.min_p", str(_SAMPLING["verify"]["min_p"])),
    # --- Sampling: reduce ---
    ("local_ai.sampling.reduce.temperature", str(_SAMPLING["reduce"]["temperature"])),
    ("local_ai.sampling.reduce.top_p", str(_SAMPLING["reduce"]["top_p"])),
    ("local_ai.sampling.reduce.top_k", str(_SAMPLING["reduce"]["top_k"])),
    ("local_ai.sampling.reduce.min_p", str(_SAMPLING["reduce"]["min_p"])),
    # --- Sampling: digest ---
    ("local_ai.sampling.digest.temperature", str(_SAMPLING["digest"]["temperature"])),
    ("local_ai.sampling.digest.top_p", str(_SAMPLING["digest"]["top_p"])),
    ("local_ai.sampling.digest.top_k", str(_SAMPLING["digest"]["top_k"])),
    ("local_ai.sampling.digest.min_p", str(_SAMPLING["digest"]["min_p"])),
    # --- Sampling: vision ---
    ("local_ai.sampling.vision.temperature", str(_SAMPLING["vision"]["temperature"])),
    ("local_ai.sampling.vision.top_p", str(_SAMPLING["vision"]["top_p"])),
]

_SEED_KEYS = [row[0] for row in _SEED_ROWS]


def upgrade() -> None:
    placeholders = ", ".join(
        f"(:k{i}, :v{i})" for i in range(len(_SEED_ROWS))
    )
    params = {}
    for i, (k, v) in enumerate(_SEED_ROWS):
        params[f"k{i}"] = k
        params[f"v{i}"] = v

    op.execute(
        text(
            f"INSERT INTO app_config (key, value) VALUES {placeholders} "
            "ON CONFLICT (key) DO NOTHING"
        ).bindparams(**params)
    )


def downgrade() -> None:
    key_list = ", ".join(f":dk{i}" for i in range(len(_SEED_KEYS)))
    params = {f"dk{i}": k for i, k in enumerate(_SEED_KEYS)}
    op.execute(
        text(f"DELETE FROM app_config WHERE key IN ({key_list})").bindparams(**params)
    )
