"""Tenant roles, their permissions, and permission checks for the signed-in user."""

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import ALL_PERMISSIONS, OWNER_ROLE, SYSTEM_ROLES
from app.models import AccessRole, AccessRolePermission, Tenant, User


def _forbidden(detail: str = "You do not have permission to do this") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def ensure_system_roles(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Create the built-in roles with their default permissions the first time a tenant needs them."""
    existing = set(
        (await session.scalars(select(AccessRole.key).where(AccessRole.tenant_id == tenant_id))).all()
    )
    missing = [role for role in SYSTEM_ROLES if role.key not in existing]
    if not missing:
        return
    for role in missing:
        await session.execute(
            insert(AccessRole)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                key=role.key,
                name=role.name,
                description=role.description,
                is_system=True,
            )
            .on_conflict_do_nothing(constraint="uq_access_role_key")
        )
    rows = (
        await session.execute(
            select(AccessRole.id, AccessRole.key).where(
                AccessRole.tenant_id == tenant_id,
                AccessRole.key.in_([role.key for role in missing]),
            )
        )
    ).all()
    ids = {key: role_id for role_id, key in rows}
    for role in missing:
        role_id = ids.get(role.key)
        if role_id is None:
            continue
        for permission in sorted(role.permissions):
            await session.execute(
                insert(AccessRolePermission)
                .values(id=uuid.uuid4(), tenant_id=tenant_id, role_id=role_id, permission=permission)
                .on_conflict_do_nothing(constraint="uq_access_role_permission")
            )
    await session.flush()


async def permissions_for(session: AsyncSession, user: User) -> frozenset[str]:
    if user.role == OWNER_ROLE:
        return ALL_PERMISSIONS
    cache_key = ("permissions", user.id, user.role)
    cached = session.info.get(cache_key)
    if cached is not None:
        return cached
    await ensure_system_roles(session, user.tenant_id)
    rows = await session.scalars(
        select(AccessRolePermission.permission)
        .join(AccessRole, AccessRole.id == AccessRolePermission.role_id)
        .where(AccessRole.tenant_id == user.tenant_id, AccessRole.key == user.role)
    )
    held = frozenset(rows.all()) & ALL_PERMISSIONS
    session.info[cache_key] = held
    return held


async def has_permission(session: AsyncSession, user: User, permission: str) -> bool:
    return permission in await permissions_for(session, user)


async def require_permission(session: AsyncSession, user: User, *permissions: str) -> frozenset[str]:
    """Pass when the user holds any of the given permissions. Returns the user's full set."""
    held = await permissions_for(session, user)
    if not any(permission in held for permission in permissions):
        raise _forbidden()
    return held


async def list_roles(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    await ensure_system_roles(session, tenant_id)
    roles = list(
        (
            await session.scalars(
                select(AccessRole)
                .options(selectinload(AccessRole.permissions))
                .where(AccessRole.tenant_id == tenant_id)
                .order_by(AccessRole.is_system.desc(), AccessRole.name)
            )
        ).all()
    )
    counts = dict(
        (
            await session.execute(
                select(User.role, func.count()).where(User.tenant_id == tenant_id).group_by(User.role)
            )
        ).all()
    )
    return [role_to_read(role, counts.get(role.key, 0)) for role in roles]


def role_to_read(role: AccessRole, user_count: int = 0) -> dict:
    permissions = ALL_PERMISSIONS if role.key == OWNER_ROLE else {item.permission for item in role.permissions}
    return {
        "id": role.id,
        "key": role.key,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "locked": role.key == OWNER_ROLE,
        "permissions": sorted(permissions & ALL_PERMISSIONS),
        "user_count": user_count,
    }


def _clean_permissions(values: list[str]) -> list[str]:
    unknown = [value for value in values if value not in ALL_PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown permission: {unknown[0]}")
    return sorted(set(values))


def _key_from_name(name: str) -> str:
    key = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    return (key or "ROLE")[:30]


async def _role(session: AsyncSession, tenant_id: uuid.UUID, role_id: uuid.UUID) -> AccessRole:
    role = await session.scalar(
        select(AccessRole)
        .options(selectinload(AccessRole.permissions))
        .where(AccessRole.id == role_id, AccessRole.tenant_id == tenant_id)
    )
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


async def _ensure_unique_name(session: AsyncSession, tenant_id: uuid.UUID, name: str, exclude_id=None) -> None:
    stmt = select(AccessRole.id).where(AccessRole.tenant_id == tenant_id, func.lower(AccessRole.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(AccessRole.id != exclude_id)
    if await session.scalar(stmt) is not None:
        raise HTTPException(status_code=409, detail="A role with this name already exists")


def _set_permissions(role: AccessRole, permissions: list[str]) -> None:
    wanted = set(permissions)
    role.permissions[:] = [item for item in role.permissions if item.permission in wanted]
    have = {item.permission for item in role.permissions}
    for permission in sorted(wanted - have):
        role.permissions.append(AccessRolePermission(tenant_id=role.tenant_id, permission=permission))


async def create_role(session: AsyncSession, tenant_id: uuid.UUID, payload) -> dict:
    await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    await ensure_system_roles(session, tenant_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    await _ensure_unique_name(session, tenant_id, name)
    base = _key_from_name(name)
    key = base
    taken = set((await session.scalars(select(AccessRole.key).where(AccessRole.tenant_id == tenant_id))).all())
    suffix = 2
    while key in taken:
        tail = f"_{suffix}"
        key = f"{base[: 30 - len(tail)]}{tail}"
        suffix += 1
    role = AccessRole(
        tenant_id=tenant_id,
        key=key,
        name=name,
        description=(payload.description or "").strip() or None,
        is_system=False,
        permissions=[],
    )
    _set_permissions(role, _clean_permissions(payload.permissions))
    session.add(role)
    await session.flush()
    return role_to_read(await _role(session, tenant_id, role.id))


async def update_role(session: AsyncSession, tenant_id: uuid.UUID, role_id: uuid.UUID, payload) -> dict:
    await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    role = await _role(session, tenant_id, role_id)
    if role.key == OWNER_ROLE:
        raise HTTPException(status_code=400, detail="The Owner role always has every permission")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    await _ensure_unique_name(session, tenant_id, name, exclude_id=role.id)
    role.name = name
    role.description = (payload.description or "").strip() or None
    _set_permissions(role, _clean_permissions(payload.permissions))
    await session.flush()
    count = await session.scalar(
        select(func.count()).select_from(User).where(User.tenant_id == tenant_id, User.role == role.key)
    )
    return role_to_read(await _role(session, tenant_id, role.id), count or 0)


async def delete_role(session: AsyncSession, tenant_id: uuid.UUID, role_id: uuid.UUID) -> None:
    await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    role = await _role(session, tenant_id, role_id)
    if role.is_system:
        raise HTTPException(status_code=400, detail="Built-in roles cannot be deleted")
    in_use = await session.scalar(
        select(func.count()).select_from(User).where(User.tenant_id == tenant_id, User.role == role.key)
    )
    if in_use:
        raise HTTPException(status_code=409, detail="Move the users on this role to another role first")
    await session.delete(role)
    await session.flush()


async def role_key_exists(session: AsyncSession, tenant_id: uuid.UUID, key: str) -> bool:
    await ensure_system_roles(session, tenant_id)
    return (
        await session.scalar(select(AccessRole.id).where(AccessRole.tenant_id == tenant_id, AccessRole.key == key))
    ) is not None


async def list_users(session: AsyncSession, tenant_id: uuid.UUID) -> list[User]:
    return list(
        (await session.scalars(select(User).where(User.tenant_id == tenant_id).order_by(User.full_name))).all()
    )


async def set_user_role(session: AsyncSession, actor: User, user_id: uuid.UUID, role_key: str) -> User:
    # Serialize role assignments within the tenant to protect the last active owner.
    await session.scalar(select(Tenant).where(Tenant.id == actor.tenant_id).with_for_update())
    target = await session.get(User, user_id)
    if target is None or target.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    key = role_key.strip().upper()
    if not await role_key_exists(session, actor.tenant_id, key):
        raise HTTPException(status_code=400, detail="Unknown role")
    if key == OWNER_ROLE and actor.role != OWNER_ROLE:
        raise HTTPException(status_code=403, detail="Only an owner can make someone an owner")
    if target.role == OWNER_ROLE and key != OWNER_ROLE:
        if actor.role != OWNER_ROLE:
            raise HTTPException(status_code=403, detail="Only an owner can change another owner's role")
        owners = await session.scalar(
            select(func.count()).select_from(User).where(User.tenant_id == actor.tenant_id, User.role == OWNER_ROLE, User.status == "ACTIVE")
        )
        if target.status == "ACTIVE" and (owners or 0) <= 1:
            raise HTTPException(status_code=400, detail="The workspace needs at least one owner")
    target.role = key
    await session.flush()
    return target
