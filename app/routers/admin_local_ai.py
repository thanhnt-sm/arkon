"""
Admin router — Local AI Orchestrator configuration + health endpoints.

Endpoints (all mounted under /api):
  GET  /admin/local-ai/config      → current LocalAIConfig (auth token masked)
  POST /admin/local-ai/config      → update config fields
  GET  /admin/local-ai/health      → LM Studio connectivity check
  POST /admin/local-ai/reset-max   → overwrite all keys with MAX_PRESET defaults
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

from app.ai.local_orchestrator.config import (
    LocalAIConfig,
    EmbeddingConfig,
    MainLLMConfig,
    SamplingProfile,
    SamplingProfiles,
    VisionConfig,
    load_config,
    save_config,
)
from app.ai.local_orchestrator.lms_client import LMSClient
from app.ai.local_orchestrator.presets import VALID_MODES

router = APIRouter()

_AUTH_TOKEN_PLACEHOLDER = "•••"

# ---------------------------------------------------------------------------
# Response / request schemas
# ---------------------------------------------------------------------------


class VisionConfigOut(BaseModel):
    model_id: str
    fallback_model_id: str
    estimated_ram_gb: float
    context_length: int
    eval_batch_size: int
    gpu_ratio: float


class MainLLMConfigOut(BaseModel):
    model_id: str
    fallback_model_id: str
    estimated_ram_gb: float
    context_length: int
    eval_batch_size: int
    gpu_ratio: float
    flash_attention: bool
    kv_cache_offload: bool


class EmbeddingConfigOut(BaseModel):
    model_id: str
    fallback_model_id: str
    estimated_ram_gb: float


class SamplingProfileOut(BaseModel):
    temperature: float
    top_p: float
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    repeat_penalty: Optional[float] = None


class SamplingProfilesOut(BaseModel):
    refine: SamplingProfileOut
    map: SamplingProfileOut
    verify: SamplingProfileOut
    reduce: SamplingProfileOut
    digest: SamplingProfileOut
    vision: SamplingProfileOut


class LocalAIConfigOut(BaseModel):
    """Config returned to the UI — auth token is masked."""

    mode: str
    lms_host: str
    lms_auth_token: str  # "" = not set; "•••" = set but hidden
    ram_headroom_gb: float
    vision: VisionConfigOut
    main_llm: MainLLMConfigOut
    embedding: EmbeddingConfigOut
    sampling: SamplingProfilesOut


class VisionConfigUpdate(BaseModel):
    model_id: Optional[str] = None
    fallback_model_id: Optional[str] = None
    estimated_ram_gb: Optional[float] = None
    context_length: Optional[int] = None
    eval_batch_size: Optional[int] = None
    gpu_ratio: Optional[float] = None


class MainLLMConfigUpdate(BaseModel):
    model_id: Optional[str] = None
    fallback_model_id: Optional[str] = None
    estimated_ram_gb: Optional[float] = None
    context_length: Optional[int] = None
    eval_batch_size: Optional[int] = None
    gpu_ratio: Optional[float] = None
    flash_attention: Optional[bool] = None
    kv_cache_offload: Optional[bool] = None


class EmbeddingConfigUpdate(BaseModel):
    model_id: Optional[str] = None
    fallback_model_id: Optional[str] = None
    estimated_ram_gb: Optional[float] = None


class LocalAIConfigUpdate(BaseModel):
    """Partial update body.

    lms_auth_token rules:
      - omitted / None  → keep existing token unchanged
      - "" (empty str)  → keep existing token unchanged
      - "•••"           → keep existing token unchanged (placeholder sent back)
      - any other str   → replace with new value
    """

    mode: Optional[str] = None
    lms_host: Optional[str] = None
    lms_auth_token: Optional[str] = None  # write-only; see masking rules above
    ram_headroom_gb: Optional[float] = None
    vision: Optional[VisionConfigUpdate] = None
    main_llm: Optional[MainLLMConfigUpdate] = None
    embedding: Optional[EmbeddingConfigUpdate] = None

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(VALID_MODES)}, got {v!r}")
        return v


class HealthOut(BaseModel):
    ok: bool
    message: str
    loaded_models: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_token(token: str) -> str:
    """Return "" if token is blank, else the placeholder."""
    return "" if not token else _AUTH_TOKEN_PLACEHOLDER


def _build_out(config: LocalAIConfig) -> LocalAIConfigOut:
    return LocalAIConfigOut(
        mode=config.mode,
        lms_host=config.lms_host,
        lms_auth_token=_mask_token(config.lms_auth_token),
        ram_headroom_gb=config.ram_headroom_gb,
        vision=VisionConfigOut(**config.vision.model_dump()),
        main_llm=MainLLMConfigOut(**config.main_llm.model_dump()),
        embedding=EmbeddingConfigOut(**config.embedding.model_dump()),
        sampling=SamplingProfilesOut(
            refine=SamplingProfileOut(**config.sampling.refine.model_dump()),
            map=SamplingProfileOut(**config.sampling.map.model_dump()),
            verify=SamplingProfileOut(**config.sampling.verify.model_dump()),
            reduce=SamplingProfileOut(**config.sampling.reduce.model_dump()),
            digest=SamplingProfileOut(**config.sampling.digest.model_dump()),
            vision=SamplingProfileOut(**config.sampling.vision.model_dump()),
        ),
    )


def _is_write_only_placeholder(token: Optional[str]) -> bool:
    """Return True when the token submitted should be treated as 'keep existing'."""
    if token is None:
        return True
    return token in ("", _AUTH_TOKEN_PLACEHOLDER)


def _apply_update(existing: LocalAIConfig, update: LocalAIConfigUpdate) -> LocalAIConfig:
    """Merge update onto existing config; returns a new LocalAIConfig."""
    data = existing.model_dump()

    if update.mode is not None:
        data["mode"] = update.mode

    if update.lms_host is not None:
        data["lms_host"] = update.lms_host

    if not _is_write_only_placeholder(update.lms_auth_token):
        data["lms_auth_token"] = update.lms_auth_token  # type: ignore[assignment]

    if update.ram_headroom_gb is not None:
        data["ram_headroom_gb"] = update.ram_headroom_gb

    if update.vision is not None:
        patch = update.vision.model_dump(exclude_none=True)
        data["vision"].update(patch)

    if update.main_llm is not None:
        patch = update.main_llm.model_dump(exclude_none=True)
        data["main_llm"].update(patch)

    if update.embedding is not None:
        patch = update.embedding.model_dump(exclude_none=True)
        data["embedding"].update(patch)

    return LocalAIConfig(**data)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/local-ai/config", response_model=LocalAIConfigOut)
async def get_local_ai_config(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
) -> LocalAIConfigOut:
    """Return current Local AI config with auth token masked."""
    config = await load_config(db)
    return _build_out(config)


@router.post("/admin/local-ai/config", response_model=LocalAIConfigOut)
async def update_local_ai_config(
    body: LocalAIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
) -> LocalAIConfigOut:
    """Partial-update Local AI config.  Auth token is write-only."""
    existing = await load_config(db)
    merged = _apply_update(existing, body)
    await save_config(db, merged)
    await log_audit(
        db, _user, "update", "local_ai_config", "global",
        reason=f"Updated local AI config; mode={merged.mode}",
    )
    await db.commit()
    return _build_out(merged)


@router.get("/admin/local-ai/health", response_model=HealthOut)
async def local_ai_health(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
) -> HealthOut:
    """Check LM Studio connectivity using the current config.

    health() returns bool; list_loaded() returns loaded model ids.
    Both are called independently so a partial failure is still informative.
    """
    config = await load_config(db)
    client = LMSClient(host=config.lms_host, auth_token=config.lms_auth_token)
    try:
        ok = await client.health()
        loaded: list[str] = []
        if ok:
            try:
                loaded = await client.list_loaded()
            except Exception:  # noqa: BLE001
                pass
        message = "LM Studio reachable" if ok else "LM Studio unreachable"
        return HealthOut(ok=ok, message=message, loaded_models=loaded)
    except Exception as exc:  # noqa: BLE001
        return HealthOut(ok=False, message=str(exc), loaded_models=[])


@router.post("/admin/local-ai/reset-max", response_model=LocalAIConfigOut)
async def reset_to_max_preset(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
) -> LocalAIConfigOut:
    """Overwrite all local_ai.* keys with MAX_PRESET defaults.

    LMS host and auth token are preserved so the operator does not need to
    re-enter connection details after a reset.
    """
    existing = await load_config(db)
    reset_config = LocalAIConfig.from_max_preset(
        preserve_host=existing.lms_host,
        preserve_token=existing.lms_auth_token,
    )
    await save_config(db, reset_config)
    await log_audit(
        db, _user, "reset", "local_ai_config", "global",
        reason="Reset local AI config to MAX_PRESET defaults",
    )
    await db.commit()
    return _build_out(reset_config)
