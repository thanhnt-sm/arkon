"""
Roles router — CRUD for custom permission roles.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Role
from app.services.auth_service import require_admin
from app.services.permissions import ALL_PERMISSIONS, PERMISSION_GROUPS, PERMISSION_LABELS

router = APIRouter(prefix="/roles", tags=["roles"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[list[str]] = None


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    permissions: list[str]
    is_system: bool

    model_config = {"from_attributes": True}


class PermissionInfo(BaseModel):
    key: str
    label: str
    group: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_permissions(perms: list[str]) -> None:
    invalid = [p for p in perms if p not in ALL_PERMISSIONS]
    if invalid:
        raise HTTPException(400, f"Unknown permissions: {invalid}")


def _to_out(role: Role) -> RoleOut:
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=role.permissions or [],
        is_system=role.is_system,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/permissions", response_model=list[PermissionInfo])
async def list_permissions(_admin=Depends(require_admin)):
    """Return all defined permission strings with labels and groups."""
    key_to_group = {
        perm: group
        for group, perms in PERMISSION_GROUPS.items()
        for perm in perms
    }
    return [
        PermissionInfo(key=k, label=PERMISSION_LABELS[k], group=key_to_group[k])
        for k in ALL_PERMISSIONS
    ]


@router.get("", response_model=list[RoleOut])
async def list_roles(
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Role).order_by(Role.is_system.desc(), Role.name))
    return [_to_out(r) for r in result.scalars().all()]


@router.post("", response_model=RoleOut, status_code=201)
async def create_role(
    body: RoleCreate,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _validate_permissions(body.permissions)
    role = Role(
        id=uuid.uuid4(),
        name=body.name.strip(),
        description=body.description,
        permissions=body.permissions,
        is_system=False,
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return _to_out(role)


@router.put("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role not found")

    if body.permissions is not None:
        _validate_permissions(body.permissions)
        role.permissions = body.permissions

    if body.description is not None:
        role.description = body.description

    # System roles: permissions can be changed but name is locked
    if body.name is not None and not role.is_system:
        role.name = body.name.strip()

    await db.flush()
    await db.refresh(role)
    return _to_out(role)


@router.delete("/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    if role.is_system:
        raise HTTPException(400, "Cannot delete system roles")
    await db.delete(role)
