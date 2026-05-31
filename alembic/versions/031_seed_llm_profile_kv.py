"""Seed LLM profile KV rows (Phase 9, MRP overhaul)

Revision ID: 031
Revises: 030
Create Date: 2026-05-24 02:30:00.000000

Inserts three KV rows into the existing `app_config` table:

    llm_profile          -> 'local' (default) or 'cloud' (auto-detected via
                            existing llm_base_url host)
    llm_context_length   -> NULL (populated by runtime_profile probe on first call)
    llm_model_name       -> NULL (populated by runtime_profile probe)

NO schema change — AppConfig is `(key PK, value Text, updated_at)`. Down
migration removes only the seed rows it added.

Auto-detect rule: if an `llm_base_url` row exists and its value matches any
of `openai.com|anthropic.com|togetherapi.com|groq.com`, seed
`llm_profile='cloud'`. Otherwise default to `'local'`. Cloud installs that
use a non-standard host pattern must run a 1-line SQL UPDATE — see
`docs/local-llm.md`.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hosts that map to cloud profile.
_CLOUD_HOST_LIKE = (
    "%openai.com%",
    "%anthropic.com%",
    "%togetherapi.com%",
    "%together.xyz%",
    "%groq.com%",
)


def upgrade() -> None:
    # Build the cloud-detect WHERE clause as a single CASE expression.
    cloud_predicate = " OR ".join(["value LIKE :p" + str(i) for i in range(len(_CLOUD_HOST_LIKE))])
    bind_params = {f"p{i}": v for i, v in enumerate(_CLOUD_HOST_LIKE)}

    op.execute(
        text(
            f"""
            INSERT INTO app_config (key, value)
            SELECT 'llm_profile',
                   CASE WHEN ({cloud_predicate}) THEN 'cloud' ELSE 'local' END
              FROM app_config
             WHERE key = 'llm_base_url'
            UNION ALL
            SELECT 'llm_profile', 'local'
             WHERE NOT EXISTS (
                 SELECT 1 FROM app_config WHERE key = 'llm_base_url'
             )
            ON CONFLICT (key) DO NOTHING
            """
        ).bindparams(**bind_params)
    )

    # Seed NULL probe results so runtime_profile re-probes on first call.
    op.execute(
        text(
            """
            INSERT INTO app_config (key, value) VALUES
                ('llm_context_length', NULL),
                ('llm_model_name', NULL),
                ('mrp.intake_paused', 'false')
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            """
            DELETE FROM app_config
             WHERE key IN (
                 'llm_profile',
                 'llm_context_length',
                 'llm_model_name',
                 'mrp.intake_paused'
             )
            """
        )
    )
