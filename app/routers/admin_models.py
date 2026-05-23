"""
Admin model-selection router for LLM and Vision capabilities.

Endpoints:
  GET  /api/settings/llm/catalog       — supported LLM models + active spec
  POST /api/settings/llm/switch        — set the active LLM spec
  GET  /api/settings/vision/catalog    — supported vision models + active spec
  POST /api/settings/vision/switch     — set the active vision spec

Mirrors the embedding catalog endpoints in admin_embeddings.py so the
settings UI can use the same dropdown pattern for all three capabilities.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter()

CUSTOM_SPEC_ID = "openai_compatible/custom"

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LLMSpecOut(BaseModel):
    id: str
    provider: str
    model_id: str
    context_window_tokens: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool
    label: str
    cost_per_1m_input_tokens: Optional[float]
    cost_per_1m_output_tokens: Optional[float]
    notes: Optional[str]
    api_key_configured: bool


class LLMCatalogOut(BaseModel):
    active_spec_id: Optional[str]
    specs: list[LLMSpecOut]
    custom_model_id: Optional[str] = None


class VisionSpecOut(BaseModel):
    id: str
    provider: str
    model_id: str
    max_image_size_mb: int
    label: str
    cost_per_1m_input_tokens: Optional[float]
    cost_per_image: Optional[float]
    notes: Optional[str]
    api_key_configured: bool


class VisionCatalogOut(BaseModel):
    active_spec_id: Optional[str]
    specs: list[VisionSpecOut]
    custom_model_id: Optional[str] = None


class SwitchBody(BaseModel):
    model_spec_id: str
    custom_model_id: Optional[str] = None  # for openai_compatible/custom only


# ---------------------------------------------------------------------------
# LLM endpoints
# ---------------------------------------------------------------------------

@router.get("/settings/llm/catalog", response_model=LLMCatalogOut)
async def get_llm_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.llm_catalog import list_specs
    from app.ai.registry import ProviderRegistry
    from app.services.config_service import ConfigService

    registry = ProviderRegistry(db)
    active = await registry.get_active_llm_spec_id()
    svc = ConfigService(db)
    api_key_configured = bool(await svc.get("llm_api_key"))
    custom_model_id = await svc.get("llm_custom_model_id")

    specs = [
        LLMSpecOut(
            id=s.id,
            provider=s.provider,
            model_id=s.model_id,
            context_window_tokens=s.context_window_tokens,
            max_output_tokens=s.max_output_tokens,
            supports_tools=s.supports_tools,
            supports_vision=s.supports_vision,
            label=s.label,
            cost_per_1m_input_tokens=s.cost_per_1m_input_tokens,
            cost_per_1m_output_tokens=s.cost_per_1m_output_tokens,
            notes=s.notes,
            api_key_configured=api_key_configured,
        )
        for s in list_specs()
    ]
    return LLMCatalogOut(active_spec_id=active, specs=specs, custom_model_id=custom_model_id)


@router.post("/settings/llm/switch")
async def switch_llm_model(
    body: SwitchBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.llm_catalog import UnknownLLMModel, get_spec
    from app.services.config_service import ACTIVE_LLM_MODEL_KEY, ConfigService

    try:
        spec = get_spec(body.model_spec_id)
    except UnknownLLMModel as e:
        raise HTTPException(status_code=400, detail=str(e))

    svc = ConfigService(db)

    # OpenAI-compatible custom spec doesn't require an API key (LM Studio, Ollama, etc.)
    is_custom = spec.id == CUSTOM_SPEC_ID
    if not is_custom and not await svc.get("llm_api_key"):
        raise HTTPException(
            status_code=400,
            detail="No LLM API key configured. Save the API key first, then switch.",
        )

    if is_custom:
        if not body.custom_model_id or not body.custom_model_id.strip():
            raise HTTPException(
                status_code=400,
                detail="custom_model_id is required when switching to openai_compatible/custom.",
            )
        await svc.set("llm_custom_model_id", body.custom_model_id.strip())

    await svc.set(ACTIVE_LLM_MODEL_KEY, spec.id)
    await log_audit(
        db, _user, "switch_llm_model", "settings", "global",
        reason=f"Switching active LLM to {spec.id}"
        + (f" model={body.custom_model_id}" if is_custom else ""),
    )
    await db.commit()
    return {"active_spec_id": spec.id}


@router.get("/settings/llm/custom/models")
async def list_custom_models(
    base_url: str = Query(..., description="Base URL of the OpenAI-compatible server"),
    api_key: str = Query(default="", description="API key (optional, e.g. 'lm-studio')"),
    _user: Employee = require_permission("org:settings:manage"),
):
    """
    Fetch the list of available models from an OpenAI-compatible server (e.g. LM Studio).
    Calls GET {base_url}/models and returns model IDs.
    """
    import httpx

    url = base_url.rstrip("/") + "/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot connect to {url}. Make sure the server is running and the URL is correct.",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Connection to {url} timed out.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching models: {e}")

    models = []
    if isinstance(data, dict) and "data" in data:
        for m in data["data"]:
            if isinstance(m, dict) and "id" in m:
                models.append({"id": m["id"], "label": m.get("id", m["id"])})
    elif isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and "id" in m:
                models.append({"id": m["id"], "label": m.get("id", m["id"])})

    return {"models": models, "url": url}


# ---------------------------------------------------------------------------
# Vision endpoints
# ---------------------------------------------------------------------------

@router.get("/settings/vision/catalog", response_model=VisionCatalogOut)
async def get_vision_catalog(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.registry import ProviderRegistry
    from app.ai.vision_catalog import list_specs
    from app.services.config_service import ConfigService

    registry = ProviderRegistry(db)
    active = await registry.get_active_vision_spec_id()
    svc = ConfigService(db)
    api_key_configured = bool(await svc.get("vision_api_key"))
    custom_model_id = await svc.get("vision_custom_model_id")

    specs = [
        VisionSpecOut(
            id=s.id,
            provider=s.provider,
            model_id=s.model_id,
            max_image_size_mb=s.max_image_size_mb,
            label=s.label,
            cost_per_1m_input_tokens=s.cost_per_1m_input_tokens,
            cost_per_image=s.cost_per_image,
            notes=s.notes,
            api_key_configured=api_key_configured,
        )
        for s in list_specs()
    ]
    return VisionCatalogOut(active_spec_id=active, specs=specs, custom_model_id=custom_model_id)


@router.post("/settings/vision/switch")
async def switch_vision_model(
    body: SwitchBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    from app.ai.vision_catalog import UnknownVisionModel, get_spec
    from app.services.config_service import ACTIVE_VISION_MODEL_KEY, ConfigService

    VISION_CUSTOM_SPEC_ID = "openai_compatible/vision-custom"

    try:
        spec = get_spec(body.model_spec_id)
    except UnknownVisionModel as e:
        raise HTTPException(status_code=400, detail=str(e))

    svc = ConfigService(db)
    is_custom = spec.id == VISION_CUSTOM_SPEC_ID

    if is_custom:
        if not body.custom_model_id or not body.custom_model_id.strip():
            raise HTTPException(
                status_code=400,
                detail="custom_model_id is required when switching to openai_compatible/vision-custom.",
            )
        await svc.set("vision_custom_model_id", body.custom_model_id.strip())
    else:
        if not await svc.get("vision_api_key"):
            raise HTTPException(
                status_code=400,
                detail="No vision API key configured. Save the API key first, then switch.",
            )

    await svc.set(ACTIVE_VISION_MODEL_KEY, spec.id)
    await log_audit(
        db, _user, "switch_vision_model", "settings", "global",
        reason=f"Switching active vision model to {spec.id}"
        + (f" model={body.custom_model_id}" if is_custom else ""),
    )
    await db.commit()
    return {"active_spec_id": spec.id}
