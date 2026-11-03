"""Company isolation for domain-bound sessions, including superuser development DBs."""
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria
from app.db.base import Base
from app.models import Company, Employee, User


def table_scope(table, company_id, visited=frozenset()):
    if table.name in visited or table.name in {"users", "tenants", "platform_admins"}:
        return None
    if table.name == "companies":
        return table.c.id == company_id
    if "company_id" in table.c:
        return table.c.company_id == company_id
    conditions = []
    for fk in table.foreign_keys:
        parent = fk.column.table
        criterion = table_scope(parent, company_id, visited | {table.name})
        if criterion is not None:
            conditions.append(fk.parent.in_(select(fk.column).where(criterion)))
    if not conditions:
        return None
    from sqlalchemy import and_
    return and_(*conditions)


@event.listens_for(Session, "do_orm_execute")
def restrict_company_queries(state):
    company_id = state.session.info.get("domain_company_id")
    if company_id is None or not (state.is_select or state.is_update or state.is_delete):
        return
    for mapper in Base.registry.mappers:
        criterion = table_scope(mapper.local_table, company_id)
        if criterion is not None:
            state.statement = state.statement.options(with_loader_criteria(mapper.class_, criterion, include_aliases=True))


@event.listens_for(Session, "before_flush")
def restrict_company_writes(session, _context, _instances):
    company_id = session.info.get("domain_company_id")
    if company_id is None:
        return
    objects = session.new | session.dirty | session.deleted
    for obj in objects:
        table = obj.__table__
        if isinstance(obj, Company):
            if obj in session.new or obj.id != company_id:
                raise HTTPException(403, "Use the main HRMS address to manage other companies")
        elif hasattr(obj, "company_id") and obj.company_id != company_id:
            raise HTTPException(403, "This address is restricted to its company")
        # Every company-scoped foreign key must also belong to this company.
        for fk in table.foreign_keys:
            criterion = table_scope(fk.column.table, company_id)
            value = getattr(obj, fk.parent.key, None)
            if criterion is None or value is None:
                continue
            pending = next((item for item in session.new if item.__table__ is fk.column.table and getattr(item, fk.column.key, None) == value), None)
            if pending is not None:
                continue  # Pending parent's own company/FKs are checked in this flush.
            exists = session.connection().scalar(select(fk.column).where(fk.column == value, criterion))
            if exists is None:
                raise HTTPException(403, "Referenced record does not belong to this company")


async def require_domain_account(request, session, user, *, employee_login=False):
    context = getattr(request.state, "company_domain", None)
    if context is None:
        return
    if user.tenant_id != context["tenant_id"]:
        raise HTTPException(403, "This account cannot sign in to this company's address")
    if employee_login or user.role == "EMPLOYEE":
        employee = await session.get(Employee, user.employee_id) if user.employee_id else None
        if employee is None or employee.company_id != context["company_id"]:
            raise HTTPException(403, "This employee account belongs to another company")
