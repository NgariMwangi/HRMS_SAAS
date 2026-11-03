import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, EmployeeSupervisor


async def list_supervisors(session: AsyncSession, employee_id: uuid.UUID) -> list[Employee]:
    links = list(
        (
            await session.scalars(
                select(EmployeeSupervisor)
                .where(EmployeeSupervisor.employee_id == employee_id)
                .order_by(EmployeeSupervisor.sort_order, EmployeeSupervisor.created_at)
            )
        ).all()
    )
    if not links:
        return []
    people = {
        row.id: row
        for row in (
            await session.scalars(
                select(Employee).where(Employee.id.in_([link.supervisor_id for link in links]))
            )
        ).all()
    }
    return [people[link.supervisor_id] for link in links if link.supervisor_id in people]


async def replace_supervisors(
    session: AsyncSession,
    employee: Employee,
    supervisor_ids: list[uuid.UUID] | None,
) -> list[Employee]:
    if supervisor_ids is None:
        return await list_supervisors(session, employee.id)
    seen: list[uuid.UUID] = []
    for supervisor_id in supervisor_ids:
        if supervisor_id == employee.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An employee cannot supervise themselves",
            )
        if supervisor_id not in seen:
            seen.append(supervisor_id)
    people: dict[uuid.UUID, Employee] = {}
    if seen:
        found = list((await session.scalars(select(Employee).where(Employee.id.in_(seen)))).all())
        people = {row.id: row for row in found}
        if len(people) != len(seen) or any(row.company_id != employee.company_id for row in people.values()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supervisor must be a fellow employee in this company",
            )
    await session.execute(
        delete(EmployeeSupervisor).where(EmployeeSupervisor.employee_id == employee.id)
    )
    for index, supervisor_id in enumerate(seen):
        session.add(
            EmployeeSupervisor(
                company_id=employee.company_id,
                employee_id=employee.id,
                supervisor_id=supervisor_id,
                sort_order=index,
            )
        )
    await session.flush()
    return [people[supervisor_id] for supervisor_id in seen]
