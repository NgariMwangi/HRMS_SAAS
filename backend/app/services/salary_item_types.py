"""Resolve existing or inline-created company payroll item titles atomically."""
from fastapi import HTTPException
from sqlalchemy import func, select, text


async def resolve_type(session, model, company_id, type_id, title, **fields):
    if type_id is not None:
        return await session.get(model, type_id)
    name = (title or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(400, "Enter a title of 1 to 100 characters")
    # Serialize inline title creation, including case variants, within a company.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"{model.__tablename__}:{company_id}:{name.lower()}"})
    row = await session.scalar(select(model).where(model.company_id == company_id,
        func.lower(model.name) == name.lower()))
    if row is None:
        row = model(company_id=company_id, name=name, is_active=True, **fields)
        session.add(row)
        await session.flush()
    return row
