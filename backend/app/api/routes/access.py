import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db
from app.core.permissions import CATALOG
from app.models import AccessRole, User
from app.schemas.access import (
    AccessRoleRead,
    AccessRoleWrite,
    AccessUserRead,
    AccessUserRoleUpdate,
    MyAccessRead,
    PermissionRead,
)
from app.services.access import (
    create_role,
    delete_role,
    list_roles,
    list_users,
    permissions_for,
    require_permission,
    set_user_role,
    update_role,
)

router = APIRouter(prefix="/access", tags=["access"])

MANAGE = "access.manage_roles"


@router.get("/me", response_model=MyAccessRead)
async def my_access(
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> MyAccessRead:
    held = await permissions_for(session, user)
    role_name = await session.scalar(
        select(AccessRole.name).where(AccessRole.tenant_id == user.tenant_id, AccessRole.key == user.role)
    )
    return MyAccessRead(
        role=user.role,
        role_name=role_name,
        permissions=sorted(held),
        employee_id=user.employee_id,
    )


@router.get("/permissions", response_model=list[PermissionRead])
async def get_permissions(
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[PermissionRead]:
    await require_permission(session, user, MANAGE)
    return [PermissionRead(key=item.key, label=item.label, group=item.group) for item in CATALOG]


@router.get("/roles", response_model=list[AccessRoleRead])
async def get_roles(
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await require_permission(session, user, MANAGE)
    return await list_roles(session, user.tenant_id)


@router.post("/roles", response_model=AccessRoleRead, status_code=status.HTTP_201_CREATED)
async def post_role(
    payload: AccessRoleWrite,
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    await require_permission(session, user, MANAGE)
    return await create_role(session, user.tenant_id, payload)


@router.patch("/roles/{role_id}", response_model=AccessRoleRead)
async def patch_role(
    role_id: uuid.UUID,
    payload: AccessRoleWrite,
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    await require_permission(session, user, MANAGE)
    return await update_role(session, user.tenant_id, role_id, payload)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role(
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> None:
    await require_permission(session, user, MANAGE)
    await delete_role(session, user.tenant_id, role_id)


@router.get("/users", response_model=list[AccessUserRead])
async def get_users(
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[User]:
    await require_permission(session, user, MANAGE)
    return await list_users(session, user.tenant_id)


@router.patch("/users/{user_id}", response_model=AccessUserRead)
async def patch_user_role(
    user_id: uuid.UUID,
    payload: AccessUserRoleUpdate,
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> User:
    await require_permission(session, user, MANAGE)
    return await set_user_role(session, user, user_id, payload.role)
