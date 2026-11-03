from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.org import blank_to_none
from app.models import Employee, EmployeeNextOfKin
from app.schemas.employee import NextOfKinWrite


async def list_next_of_kin(
    session: AsyncSession, employee_id
) -> list[EmployeeNextOfKin]:
    result = await session.scalars(
        select(EmployeeNextOfKin)
        .where(EmployeeNextOfKin.employee_id == employee_id)
        .order_by(EmployeeNextOfKin.sort_order, EmployeeNextOfKin.created_at)
    )
    return list(result.all())


async def replace_next_of_kin(
    session: AsyncSession,
    employee: Employee,
    items: list[NextOfKinWrite] | None,
) -> list[EmployeeNextOfKin]:
    if items is None:
        return await list_next_of_kin(session, employee.id)
    await session.execute(
        delete(EmployeeNextOfKin).where(EmployeeNextOfKin.employee_id == employee.id)
    )
    rows: list[EmployeeNextOfKin] = []
    for index, item in enumerate(items):
        row = EmployeeNextOfKin(
            company_id=employee.company_id,
            employee_id=employee.id,
            name=item.name,
            relationship=item.relationship,
            phone=item.phone,
            other_phone=blank_to_none(item.other_phone or ""),
            email=str(item.email).lower() if item.email else None,
            address=blank_to_none(item.address or ""),
            sort_order=index,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows
