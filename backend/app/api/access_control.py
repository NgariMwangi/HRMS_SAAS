"""Reusable permission dependencies and server-side employee visibility scopes."""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db
from app.models import Company, Employee, EmployeeSupervisor, User
from app.services.access import permissions_for, require_permission


def require_access(*permissions: str):
    async def check(
        session: AsyncSession = Depends(get_tenant_db),
        user: User = Depends(get_current_user),
    ) -> None:
        await require_permission(session, user, *permissions)
    return check


async def employee_scope(session: AsyncSession, user: User, area: str = "people"):
    held = await permissions_for(session, user)
    if f"{area}.view_all" in held or f"{area}.manage" in held:
        return Employee.company_id.in_(select(Company.id).where(Company.tenant_id == user.tenant_id))
    conditions = []
    if f"{area}.view_own" in held and user.employee_id is not None:
        conditions.append(Employee.id == user.employee_id)
    if f"{area}.view_team" in held and user.employee_id is not None:
        conditions.append(Employee.id.in_(select(EmployeeSupervisor.employee_id).where(
            EmployeeSupervisor.supervisor_id == user.employee_id,
            EmployeeSupervisor.company_id.in_(select(Company.id).where(Company.tenant_id == user.tenant_id)),
        )))
    if not conditions:
        return Employee.id.in_([])
    return or_(*conditions)


def require_employee_access(*areas: str):
    async def check(
        employee_id: uuid.UUID,
        session: AsyncSession = Depends(get_tenant_db),
        user: User = Depends(get_current_user),
    ) -> None:
        visible = await session.scalar(select(Employee.id).where(
            Employee.id == employee_id, or_(*[await employee_scope(session, user, area) for area in areas]),
            Employee.company_id.in_(select(Company.id).where(Company.tenant_id == user.tenant_id)),
        ))
        if visible is None:
            raise HTTPException(status_code=404, detail="Employee not found")
    return check
