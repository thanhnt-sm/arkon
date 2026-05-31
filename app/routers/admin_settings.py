"""
Admin settings router — provider config, connection testing, dashboard stats.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Department, Employee, Source
from app.database.repository import Repository
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user, require_permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_sources: int
    total_departments: int
    total_employees: int


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    repo = Repository(db)
    return DashboardStats(
        total_sources=await repo.count(Source),
        total_departments=await repo.count(Department),
        total_employees=await repo.count(Employee),
    )


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------

class SettingsUpdate(BaseModel):
    """Batch update config values."""
    settings: dict[str, str]


class TestConnectionResult(BaseModel):
    success: bool
    message: str
    details: Optional[dict] = None


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    """Get current app settings (masked sensitive values for UI)."""
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    ui_config = await svc.get_all_for_ui()
    return ui_config


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    """Update config values in database."""
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    results = await svc.set_batch(body.settings)
    
    # Audit log
    keys_updated = list(body.settings.keys())
    await log_audit(db, _user, "update", "settings", "global", reason=f"Updated keys: {', '.join(keys_updated)}")
    
    # Auto-sync Local AI config if model-related settings were changed
    model_keys = {
        "active_llm_model_spec_id", "llm_custom_model_id", "llm_base_url",
        "active_vision_model_spec_id", "vision_custom_model_id", "vision_base_url",
        "active_embedding_model_spec_id", "embedding_custom_model_id", "embedding_base_url"
    }
    if any(k in model_keys for k in keys_updated):
        try:
            from app.routers.admin_local_ai import (
                _resolve_settings_models,
                _apply_settings_models,
                _reset_router_best_effort
            )
            from app.ai.local_orchestrator.config import load_config, save_config
            
            existing = await load_config(db)
            settings_models = await _resolve_settings_models(db)
            synced = _apply_settings_models(existing, settings_models)
            await save_config(db, synced)
            await _reset_router_best_effort()
        except Exception:
            pass

    await db.commit()
    return {"updated": results}


# ---------------------------------------------------------------------------
# Provider connection testing
# ---------------------------------------------------------------------------

@router.post("/settings/test-providers", response_model=dict[str, TestConnectionResult])
async def test_all_providers(db: AsyncSession = Depends(get_db)):
    """Test all configured AI providers (embedding, LLM, vision)."""
    from app.ai.registry import ProviderRegistry

    registry = ProviderRegistry(db)
    results = await registry.test_all()

    return {
        capability: TestConnectionResult(success=ok, message=msg)
        for capability, (ok, msg) in results.items()
    }


@router.post("/settings/test-embedding", response_model=TestConnectionResult)
async def test_embedding(db: AsyncSession = Depends(get_db)):
    """Test the configured embedding provider."""
    from app.ai.registry import ProviderRegistry

    try:
        registry = ProviderRegistry(db)
        provider = await registry.get_embedding()
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


@router.post("/settings/test-llm", response_model=TestConnectionResult)
async def test_llm(db: AsyncSession = Depends(get_db)):
    """Test the configured LLM provider."""
    from app.ai.registry import ProviderRegistry

    try:
        registry = ProviderRegistry(db)
        provider = await registry.get_llm()
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


@router.post("/settings/test-vision", response_model=TestConnectionResult)
async def test_vision(db: AsyncSession = Depends(get_db)):
    """Test the configured vision provider."""
    from app.ai.registry import ProviderRegistry

    try:
        registry = ProviderRegistry(db)
        provider = await registry.get_vision()
        if not provider:
            return TestConnectionResult(success=False, message="No vision provider configured")
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


# ---------------------------------------------------------------------------
# LLM runtime health (Phase 4) — admin only
# ---------------------------------------------------------------------------

@router.get("/llm-health")
async def get_llm_health(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
) -> dict:
    """
    Snapshot of LM Studio liveness + active runtime profile knobs.
    Admin-only because it leaks operational fingerprint (model name, base url).
    """
    from app.ai.mrp.pipeline import get_health_snapshot
    from app.services.config_service import ConfigService

    cfg = ConfigService(db)
    snap = get_health_snapshot()
    return {
        "profile": await cfg.get("llm_profile"),
        "context_length": await cfg.get("llm_context_length"),
        "model_name": await cfg.get("llm_model_name"),
        "intake_paused": (await cfg.get("mrp.intake_paused")) == "true",
        **snap,
    }


# ---------------------------------------------------------------------------
# App config PATCH (Phase 9) — admin only, allowlisted keys
# ---------------------------------------------------------------------------

_ALLOWED_PATCH_KEYS = {"llm_profile", "mrp.intake_paused"}


class AppConfigPatch(BaseModel):
    """Partial app-config update body. Only allowlisted keys are honored."""
    updates: dict[str, str]


@router.patch("/app-config")
async def patch_app_config(
    body: AppConfigPatch,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
) -> dict:
    """
    Update a small set of operational config keys.
    On `llm_profile` change, invalidates the runtime-profile cache so the
    next ingest sees the new value within 1 request (not 60s TTL).
    """
    from app.services.config_service import ConfigService

    cfg = ConfigService(db)
    applied: dict[str, str] = {}
    for k, v in body.updates.items():
        if k not in _ALLOWED_PATCH_KEYS:
            continue
        await cfg.set(k, str(v))
        applied[k] = str(v)

    await db.commit()

    if "llm_profile" in applied:
        try:
            from app.ai.runtime_profile import invalidate
            invalidate()
        except Exception:
            pass

    await log_audit(
        db, _user, "patch", "app-config", "global",
        reason=f"Updated keys: {', '.join(applied.keys()) or 'none'}",
    )
    await db.commit()
    return {"updated": applied}


# ---------------------------------------------------------------------------
# Supported providers list (for admin UI dropdowns)
# ---------------------------------------------------------------------------

@router.get("/settings/providers")
async def list_providers():
    """
    Catalog-derived listing of supported providers per capability. Each model
    entry includes spec_id, label, cost, and capability metadata so the UI can
    render rich dropdowns.
    """
    from app.ai.registry import supported_providers
    return supported_providers()
