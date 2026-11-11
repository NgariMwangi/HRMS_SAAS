"""Transactional legacy HRMS import; defaults to a full rollback rehearsal.

Consumes protected JSON snapshots and organization mappings, not credentials.
Financial history is copied as snapshots, never recalculated with current packs.
"""
import argparse
import asyncio
import calendar
import hashlib
import json
import mimetypes
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Date, DateTime, Numeric, and_, or_, insert, select, text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from app.core.config import get_settings
from app.core.permissions import SYSTEM_ROLES
from app.db.base import Base
from app.models import *  # Register all foreign key targets.
from app.models.legacy_import import LegacyImportRecord
from app.services.access import ensure_system_roles
from app.services.leave_balances import entitled_days
from scripts.prepare_legacy_organization import legacy_id

D = Decimal


def amount(value):
    return D(str(value or 0)).quantize(D("0.01"))


def day(value):
    return date.fromisoformat(str(value)[:10]) if value else None


def parsed(value):
    return json.loads(value) if isinstance(value, str) else value


def scrub(value):
    if isinstance(value, dict):
        return {key: "[redacted]" if any(word in key.lower() for word in ["password", "secret", "token", "api_key"])
                else scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str) and value[:1] in {"{", "["}:
        try:
            return scrub(json.loads(value))
        except (ValueError, TypeError):
            pass
    return value


class Importer:
    def __init__(self, snapshot, mapping, fingerprint, uploads_root=None):
        self.snapshot = snapshot
        self.source = snapshot["tables"]
        self.maps = defaultdict(dict)
        for name in ["companies", "branches"]:
            self.maps[name] = {int(key): uuid.UUID(value) for key, value in mapping[name].items()}
        self.tenant = uuid.UUID(mapping["tenant_id"])
        self.owner_id = uuid.UUID(mapping["preserved_owner_id"])
        self.fingerprint = fingerprint
        self.rows = defaultdict(list)
        self.destinations = defaultdict(list)
        self.people = {r["id"]: r for r in self.source["employees"]}
        self.consultants = {r["id"]: r for r in self.source["consultants"]}
        self.branches = {r["id"]: r for r in self.source["branches"]}
        self.runs = {r["id"]: r for r in self.source["payroll_runs"]}
        self.compensations = defaultdict(list)
        self.run_ids = {}
        self.branch_currency = {}
        self.warnings = []
        self.written = defaultdict(int)
        self.uploads_root = Path(uploads_root).resolve() if uploads_root else None
        self.files_copied = 0

    def file(self, source_path):
        if not source_path:
            return None
        if self.uploads_root is None:
            raise ValueError("The snapshot references files; provide --uploads-root")
        name = str(source_path).replace("\\", "/")
        prefix = "/tmp/hrms/uploads/"
        if name.startswith(prefix):
            name = name[len(prefix):]
        candidate = (self.uploads_root / name).resolve()
        if not candidate.is_relative_to(self.uploads_root):
            raise ValueError("A source file reference escapes the uploads directory")
        if not candidate.is_file():
            self.warnings.append(f"Original upload is missing from source storage: {name}")
            return None
        self.files_copied += 1
        return candidate.name, mimetypes.guess_type(candidate.name)[0] or "application/octet-stream", candidate.read_bytes()

    def identity(self, table, source_id):
        if source_id is None:
            return None
        if source_id not in self.maps[table]:
            self.maps[table][source_id] = legacy_id(table, source_id)
        return self.maps[table][source_id]

    def company(self, old_id):
        return self.identity("companies", old_id)

    def add(self, table, row, source_table=None, source_id=None):
        self.rows[table].append(row)
        if source_table is not None:
            self.destinations[(source_table, source_id)].append((table, row["id"]))
        return row["id"]

    async def write(self, session, table):
        rows = self.rows[table][self.written[table]:]
        metadata = Base.metadata.tables[table]
        groups = defaultdict(list)
        for row in rows:
            result = {}
            for key, value in row.items():
                column = metadata.c[key]
                if value is not None:
                    if isinstance(column.type, UUID):
                        value = uuid.UUID(str(value))
                    elif isinstance(column.type, DateTime) and isinstance(value, str):
                        value = datetime.fromisoformat(value)
                        if column.type.timezone and value.tzinfo is None:
                            value = value.replace(tzinfo=timezone.utc)
                        elif not column.type.timezone and value.tzinfo is not None:
                            value = value.replace(tzinfo=None)
                    elif isinstance(column.type, Date) and isinstance(value, str):
                        value = day(value)
                    elif isinstance(column.type, Numeric):
                        value = D(str(value))
                result[key] = value
            groups[tuple(sorted(result))].append(result)
        for batch in groups.values():
            for start in range(0, len(batch), 500):
                await session.execute(insert(metadata), batch[start:start + 500])
        print(f"Prepared {table}: {len(rows)}", flush=True)
        self.written[table] = len(self.rows[table])

    async def prepare(self, session):
        for branch_id in self.branches:
            if branch_id not in self.maps["branches"]:
                raise ValueError(f"Branch mapping missing for source branch {branch_id}")
            branch = await session.get(Branch, self.identity("branches", branch_id))
            if branch is None or branch.company_id != self.company(self.branches[branch_id]["company_id"]):
                raise ValueError("Organization mapping does not match the destination")
            country = await session.get(Country, branch.country_id)
            self.branch_currency[branch_id] = branch.currency_id or country.default_currency_id
        existing_owner = await session.get(User, self.owner_id)
        if existing_owner is None or existing_owner.tenant_id != self.tenant or existing_owner.role != "OWNER":
            raise ValueError("The existing workspace owner must be preserved")
        for table in [Employee, PayrollRun, EmployeeCompensation, LeaveRequest]:
            if await session.scalar(select(func.count()).select_from(table)):
                raise ValueError(f"Destination {table.__tablename__} is not empty; refusing to overwrite business data")
        for row in self.source["document_categories"]:
            company_id = self.company(row["company_id"])
            existing = await session.scalar(select(DocumentCategory).where(DocumentCategory.company_id == company_id,
                func.lower(DocumentCategory.name) == row["name"].strip().lower()))
            if existing is not None:
                self.maps["document_categories"][row["id"]] = existing.id
            else:
                self.add("document_categories", dict(id=self.identity("document_categories", row["id"]), company_id=company_id,
                    name=row["name"], system_key=None, locked=False, sort_order=100 + row["id"]), "document_categories", row["id"])
        await self.write(session, "document_categories")
        for row in self.source["public_holidays"]:
            company_id = self.company(row["company_id"])
            country = await session.scalar(select(Country).where(Country.code == row["country_code"]))
            recurring = row["kind"] == "recurring"
            same_date = and_(PublicHoliday.kind == "YEARLY", PublicHoliday.month == row.get("recurring_month"), PublicHoliday.day == row.get("recurring_day")) if recurring else and_(PublicHoliday.kind == "ONCE", PublicHoliday.observed_on == day(row["date"]))
            existing = await session.scalar(select(PublicHoliday).where(PublicHoliday.company_id == company_id,
                or_(func.lower(PublicHoliday.name) == row["name"].strip().lower(), same_date)))
            if existing is not None and existing.country_id == country.id:
                self.maps["public_holidays"][row["id"]] = existing.id
                continue
            name = f"{row['name']} ({row['country_code']})" if existing else row["name"]
            self.add("public_holidays", dict(id=self.identity("public_holidays", row["id"]), company_id=company_id,
                country_id=country.id, name=name, kind="YEARLY" if recurring else "ONCE",
                observed_on=None if recurring else row["date"], month=row.get("recurring_month") if recurring else None,
                day=row.get("recurring_day") if recurring else None), "public_holidays", row["id"])
        await self.write(session, "public_holidays")
        for table in ["departments", "job_titles"]:
            names = {}
            for row in self.source[table]:
                company_id = self.company(row["company_id"])
                key = (company_id, row["name"].strip().lower())
                if key in names:
                    display_name = f"{row['name']} ({row.get('code') or row['id']})"
                else:
                    display_name = row["name"]
                identity = self.identity(table, row["id"])
                names[key] = identity
                self.add(table, dict(id=identity, company_id=company_id, name=display_name, code=row.get("code"),
                    description=row.get("description"), status="ACTIVE"), table, row["id"])
            await self.write(session, table)
        statuses = {"active": "ACTIVE", "on_leave": "ACTIVE", "suspended": "SUSPENDED", "terminated": "TERMINATED", "resigned": "TERMINATED", "retired": "TERMINATED"}
        employment = {"permanent": "FULL_TIME", "full_time": "FULL_TIME", "contract": "CONTRACT", "probation": "PROBATION", "intern": "INTERN", "casual": "CONTRACT"}
        for row in self.people.values():
            if row["status"].lower() not in statuses:
                raise ValueError(f"Unmapped employee status {row['status']}")
            identity = self.identity("employees", row["id"])
            entry = dict(id=identity, company_id=self.company(row["company_id"]), branch_id=self.identity("branches", row["branch_id"]),
                department_id=self.identity("departments", row.get("department_id")), job_title_id=self.identity("job_titles", row.get("job_title_id")),
                employee_number=row.get("employee_number") or f"LEGACY-{row['id']:04d}", first_name=row["first_name"],
                last_name=row["last_name"], other_names=row.get("middle_name"), date_of_birth=row.get("date_of_birth"),
                id_number=row.get("national_id") or None, pin_number=row.get("kra_pin") or None,
                nssf_no=row.get("nssf_number") or None, shif_no=row.get("nhif_number") or None,
                email=(row.get("email") or "").strip() or None, personal_email=(row.get("secondary_email") or "").strip() or None,
                phone=row.get("phone"), other_phone=row.get("secondary_phone") or row.get("phone_alt"),
                employment_type=employment.get((row.get("employment_type") or "permanent").lower(), "FULL_TIME"),
                date_joined=row.get("hire_date"), date_ended=row.get("termination_date") or row.get("contract_end_date"),
                status=statuses[row["status"].lower()], prorate_payroll=row.get("prorate_payroll", True),
                bank_name=row.get("bank_name"), bank_branch=row.get("bank_branch"), bank_account_number=row.get("bank_account_number"),
                bank_code=row.get("bank_code"), swift_code=row.get("swift_code"))
            photo = self.file(row.get("photo_url"))
            if photo:
                entry.update(photo_content_type=photo[1], photo_bytes=photo[2])
            self.add("employees", entry, "employees", row["id"])
        await self.write(session, "employees")
        for row in self.people.values():
            if row.get("manager_id") and row["manager_id"] != row["id"]:
                manager = self.people[row["manager_id"]]
                if manager["company_id"] != row["company_id"]:
                    raise ValueError("Cross-company supervisor relationship in source")
                self.add("employee_supervisors", dict(id=legacy_id("supervisors", row["id"]), company_id=self.company(row["company_id"]),
                    employee_id=self.identity("employees", row["id"]), supervisor_id=self.identity("employees", row["manager_id"]), sort_order=0))
            if row.get("emergency_contact_name") and row.get("emergency_contact_phone"):
                self.add("employee_next_of_kin", dict(id=legacy_id("contacts", row["id"]), company_id=self.company(row["company_id"]),
                    employee_id=self.identity("employees", row["id"]), name=row["emergency_contact_name"],
                    relationship="Not specified", phone=row["emergency_contact_phone"], sort_order=0))
        await self.write(session, "employee_supervisors")
        await self.write(session, "employee_next_of_kin")
        await self.users(session, existing_owner)
        await self.salaries(session)
        await self.schedules(session)
        await self.leave(session)
        await self.payroll(session)
        await self.consultant_records(session)
        await self.overtime(session)
        await self.archive(session)

    async def users(self, session, existing_owner):
        await ensure_system_roles(session, self.tenant)
        roles = {r["id"]: r["code"] for r in self.source["roles"]}
        assignments = defaultdict(set)
        for row in self.source["user_roles"]:
            assignments[row["user_id"]].add(roles[row["role_id"]])
        # The old source allows assigned managers to review leave even when their
        # login has EMPLOYEE role. Preserve that scoped capability without HR grants.
        employee_permissions = next(r.permissions for r in SYSTEM_ROLES if r.key == "EMPLOYEE")
        for key, name, permissions in [
            ("LEGACY_SUPERVISOR", "Imported supervisor", employee_permissions | {"leave.view_team"}),
            ("LEGACY_FINANCE", "Imported finance reviewer", {"reports.view", "payroll.view_own"}),
        ]:
            role_id = legacy_id("access_roles", key)
            self.add("access_roles", dict(id=role_id, tenant_id=self.tenant, key=key, name=name,
                description="Imported legacy role; no platform administration grants", is_system=False))
            for permission in permissions:
                self.add("access_role_permissions", dict(id=legacy_id("role_permissions", f"{key}/{permission}"),
                    tenant_id=self.tenant, role_id=role_id, permission=permission))
        await self.write(session, "access_roles")
        await self.write(session, "access_role_permissions")
        supervisors = {r["manager_id"] for r in self.people.values() if r.get("manager_id")}
        for row in self.source["users"]:
            existing = await session.scalar(select(User).where(func.lower(User.email) == row["email"].strip().lower()))
            if existing is not None:
                if existing.id != existing_owner.id or existing.tenant_id != self.tenant:
                    raise ValueError("A source login conflicts with an existing destination account")
                self.maps["users"][row["id"]] = existing.id
                self.destinations[("users", row["id"])].append(("users", existing.id))
                continue
            assigned = assignments[row["id"]]
            role = "ADMIN" if "ADMIN" in assigned or row.get("is_superuser") else "HR" if assigned & {"HR_MANAGER", "HR_STAFF"} else "MANAGER" if "MANAGER" in assigned else "LEGACY_FINANCE" if "FINANCE_PAYROLL_APPROVER" in assigned else "LEGACY_SUPERVISOR" if row.get("employee_id") in supervisors else "EMPLOYEE"
            if role == "LEGACY_FINANCE":
                self.warnings.append("Imported finance reviewer has read-only reporting access; grant broader payroll management only after owner review")
            employee = self.people.get(row.get("employee_id"))
            name = " ".join(filter(None, [employee.get("first_name"), employee.get("middle_name"), employee.get("last_name")])) if employee else row["email"]
            self.add("users", dict(id=self.identity("users", row["id"]), tenant_id=self.tenant, email=row["email"].strip(),
                password_hash=row["password_hash"], full_name=name, role=role, status="ACTIVE" if row["is_active"] else "INACTIVE",
                employee_id=self.identity("employees", row.get("employee_id"))), "users", row["id"])
        await self.write(session, "users")

    async def salaries(self, session):
        allowance_catalog = {r["id"]: r for r in self.source["allowances"]}
        for person in self.people.values():
            salaries = sorted([r for r in self.source["employee_salaries"] if r["employee_id"] == person["id"]], key=lambda r: r["effective_from"])
            assignments = [r for r in self.source["employee_allowances"] if r["employee_id"] == person["id"]]
            boundaries = {day(r["effective_from"]) for r in salaries + assignments}
            from datetime import timedelta
            boundaries |= {day(r["effective_to"]) + timedelta(days=1) for r in assignments if r.get("effective_to")}
            for start in sorted(boundaries):
                applicable = [r for r in salaries if day(r["effective_from"]) <= start and (not r.get("effective_to") or day(r["effective_to"]) >= start)]
                if not applicable:
                    continue
                row = applicable[-1]
                identity = legacy_id("salary_versions", f"{person['id']}/{start}")
                self.maps["employee_salaries"].setdefault(row["id"], identity)
                self.compensations[person["id"]].append((start, identity))
                self.add("employee_compensation", dict(id=identity, company_id=self.company(person["company_id"]),
                    employee_id=self.identity("employees", person["id"]), effective_from=start, structure="BASIC_PLUS_ALLOWANCES",
                    basic_amount=amount(row["basic_salary"]), gross_amount=None, voluntary_pension=amount(row.get("pension_employee_fixed_amount")),
                    pension_scheme="Imported voluntary pension" if amount(row.get("pension_employee_fixed_amount")) else None,
                    currency_id=self.branch_currency[person["branch_id"]], is_historical=False), "employee_salaries", row["id"])
                active_assignments = [a for a in assignments if day(a["effective_from"]) <= start and (not a.get("effective_to") or day(a["effective_to"]) >= start)]
                catalog_codes = {(allowance_catalog[a["allowance_id"]].get("code") or "").upper() for a in active_assignments}
                lines = [(name, amount(row.get(field))) for field, name, code in [("house_allowance", "House allowance", "HOUSE"),
                    ("transport_allowance", "Transport allowance", "TRANSPORT"), ("meal_allowance", "Meal allowance", "MEAL"), ("other_allowances", "Other allowances", "OTHER_ALLOW")] if code not in catalog_codes]
                lines += [(allowance_catalog[a["allowance_id"]]["name"], amount(a["amount"])) for a in active_assignments]
                for index, (name, value) in enumerate(lines):
                    if value:
                        self.add("employee_pay_lines", dict(id=legacy_id("pay_lines", f"{identity}/{index}"), compensation_id=identity,
                            kind="ALLOWANCE", name=name, amount=value, sort_order=index))
        await self.write(session, "employee_compensation")
        await self.write(session, "employee_pay_lines")

    async def schedules(self, session):
        catalog = {}
        recovered = defaultdict(lambda: D(0))
        for slip in self.source["payroll_items"]:
            if self.runs[slip["payroll_run_id"]]["status"] not in {"approved", "finance_reviewed", "paid"}:
                continue
            for line in parsed(slip["deductions_breakdown"]) or []:
                code = line.get("code", "")
                if code.startswith("DED_") and code[4:].isdigit():
                    recovered[int(code[4:])] += amount(line["amount"])
        legacy_catalog = {r["id"]: r for r in self.source["deductions"]}
        for table, kind in [("employee_deductions", "deduction_types"), ("employee_benefits", "benefit_types")]:
            for row in self.source[table]:
                person = self.people[row["employee_id"]]
                value = amount(row["amount"])
                if value <= 0:
                    self.warnings.append(f"{table}/{row['id']}: zero-value schedule preserved in imported history")
                    continue
                title = row.get("title") or legacy_catalog.get(row.get("deduction_id"), {}).get("name") or "Imported deduction"
                key = (kind, person["company_id"], title.strip().lower())
                if key not in catalog:
                    catalog[key] = legacy_id(kind, f"{person['company_id']}/{title.strip().lower()}")
                    data = dict(id=catalog[key], company_id=self.company(person["company_id"]), name=title,
                        default_amount=None, is_active=True)
                    if kind == "deduction_types":
                        data["category"] = "PERSONAL"
                    self.add(kind, data)
                if table == "employee_deductions":
                    if row.get("calculation_mode", "fixed") != "fixed":
                        raise ValueError("Percentage deduction requires an explicit migration rule")
                    data = dict(deduction_type_id=catalog[key], frequency="RECURRING", amount=value,
                        start_date=row["effective_from"], end_date=row.get("effective_to"),
                        total_amount=amount(row["remaining_balance"]) + recovered[row["id"]] if row.get("remaining_balance") is not None else None,
                        reference=f"Legacy deduction {row['id']}")
                else:
                    if row.get("payroll_year") and row.get("payroll_month"):
                        start = date(row["payroll_year"], row["payroll_month"], 1)
                    else:
                        start = day(row.get("effective_date"))
                    if start is None:
                        raise ValueError(f"Benefit {row['id']} has no effective date or payroll month")
                    data = dict(benefit_type_id=catalog[key], frequency="RECURRING" if row["frequency"] == "monthly" else "ONE_OFF",
                        amount=value, start_date=start, end_date=None, note=None)
                data.update(id=self.identity(table, row["id"]), company_id=self.company(person["company_id"]),
                    employee_id=self.identity("employees", person["id"]), status="ACTIVE" if row["is_active"] else "STOPPED")
                self.add(table, data, table, row["id"])
        for table in ["deduction_types", "benefit_types", "employee_deductions", "employee_benefits"]:
            await self.write(session, table)

    async def leave(self, session):
        categories = {}
        for row in self.source["leave_types"]:
            entry = dict(id=self.identity("leave_types", row["id"]), company_id=self.company(row["company_id"]),
                name=row["name"], days=amount(row.get("days_per_year")), accrued=row["accrues_monthly"],
                accrual_per_month=amount(row.get("days_per_month")), day_basis=row.get("days_count_basis", "working").upper(), sort_order=row["id"])
            categories[row["id"]] = entry
            self.add("leave_types", entry, "leave_types", row["id"])
        await self.write(session, "leave_types")
        usage = defaultdict(lambda: D(0))
        pending = defaultdict(lambda: D(0))
        for row in self.source["leave_requests"]:
            person = self.people[row["employee_id"]]
            identity = self.identity("leave_requests", row["id"])
            status = {"pending": "PENDING_SUPERVISOR", "pending_hr": "PENDING_HR", "approved": "APPROVED", "rejected": "REJECTED", "cancelled": "CANCELLED"}[row["status"]]
            key = (person["id"], row["leave_type_id"], day(row["start_date"]).year)
            if status == "APPROVED":
                usage[key] += amount(row["days_requested"])
            elif status.startswith("PENDING"):
                pending[key] += amount(row["days_requested"])
            self.add("leave_requests", dict(id=identity, company_id=self.company(person["company_id"]),
                employee_id=self.identity("employees", person["id"]), leave_type_id=self.identity("leave_types", row["leave_type_id"]),
                start_on=row["start_date"], end_on=row["end_date"], days=amount(row["days_requested"]), reason=row.get("reason"),
                requested_as="EMPLOYEE", approval_mode="SUPERVISOR_THEN_HR", status=status,
                requested_by_user_id=None, requested_by_employee_id=self.identity("employees", person["id"]),
                created_at=row["created_at"]), "leave_requests", row["id"])
            for step, actor, timestamp, note in [
                ("SUPERVISOR", row.get("supervisor_reviewed_by_id"), row.get("supervisor_reviewed_at"), row.get("supervisor_notes")),
                ("HR", row.get("reviewed_by_id"), row.get("reviewed_at"), row.get("review_notes"))]:
                if timestamp:
                    decision = "REJECTED" if status == "REJECTED" and (step == "HR" or not row.get("reviewed_at")) else "APPROVED"
                    self.add("leave_decisions", dict(id=legacy_id("leave_decisions", f"{row['id']}/{step}"),
                        company_id=self.company(person["company_id"]), leave_request_id=identity, step=step, decision=decision,
                        note=note, actor_user_id=self.identity("users", actor), actor_employee_id=None, created_at=timestamp))
        await self.write(session, "leave_requests")
        await self.write(session, "leave_decisions")
        for row in self.source["leave_requests"]:
            file = self.file(row.get("document_path"))
            if not file:
                continue
            person = self.people[row["employee_id"]]
            company_id = self.company(person["company_id"])
            category = await session.scalar(select(DocumentCategory).where(DocumentCategory.company_id == company_id,
                DocumentCategory.system_key == "PERSONAL"))
            if category is None:
                raise ValueError("Personal document category is missing")
            self.add("employee_documents", dict(id=legacy_id("leave_documents", row["id"]), company_id=company_id,
                employee_id=self.identity("employees", person["id"]), category_id=category.id,
                filename=file[0], content_type=file[1], file_bytes=file[2],
                note=f"Imported attachment for legacy leave request #{row['id']}", uploaded_by=None,
                created_at=row["created_at"]), "leave_requests", row["id"])
        await self.write(session, "employee_documents")
        cutoff = datetime.fromisoformat(self.snapshot["captured_at"]).date()
        self.balance_checks = []
        for row in self.source["leave_balances"]:
            person = self.people[row["employee_id"]]
            key = (person["id"], row["leave_type_id"], row["year"])
            category = SimpleNamespace(**categories[row["leave_type_id"]])
            entitlement = entitled_days(category, day(person.get("hire_date")), row["year"], cutoff)
            # Source closing excludes pending applications; target available balance
            # reserves them separately. Keep the same unreserved closing amount.
            extra = amount(row["closing_balance"]) + usage[key] - entitlement
            self.add("leave_balances", dict(id=self.identity("leave_balances", row["id"]), company_id=self.company(person["company_id"]),
                employee_id=self.identity("employees", person["id"]), leave_type_id=self.identity("leave_types", row["leave_type_id"]),
                year=row["year"], extra_days=extra), "leave_balances", row["id"])
            self.balance_checks.append(dict(employee_id=person["id"], year=row["year"],
                source_closing=str(amount(row["closing_balance"])), target_before_reservations=str(entitlement+extra-usage[key]),
                pending_reserved=str(pending[key])))
        await self.write(session, "leave_balances")

    def branch_at(self, employee_id, end, country_code):
        person = self.people[employee_id]
        history = [r for r in self.source["employee_assignment_history"] if r["employee_id"] == employee_id
            and day(r["effective_from"]) <= end and r.get("branch_id")
            and self.branches[r["branch_id"]]["country_code"] == country_code]
        if history:
            return max(history, key=lambda r: (r["effective_from"], r["id"]))["branch_id"]
        if self.branches[person["branch_id"]]["country_code"] == country_code:
            return person["branch_id"]
        raise ValueError(f"Cannot resolve historical branch for employee {employee_id} in {country_code}")

    async def payroll(self, session):
        pays_by_run = defaultdict(list)
        for slip in self.source["payroll_items"]:
            pays_by_run[slip["payroll_run_id"]].append(slip)
        for source_run in self.source["payroll_runs"]:
            start = date(source_run["pay_year"], source_run["pay_month"], 1)
            end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
            branch_ids = [r["id"] for r in self.branches.values() if r["company_id"] == source_run["company_id"] and r["country_code"] == source_run["country_code"]]
            split = defaultdict(list)
            for slip in pays_by_run[source_run["id"]]:
                split[self.branch_at(slip["employee_id"], end, source_run["country_code"])].append(slip)
            country = await session.scalar(select(Country).where(Country.code == source_run["country_code"]))
            pack = await session.scalar(select(PayrollPack).where(PayrollPack.country_id == country.id,
                PayrollPack.status == "PUBLISHED", PayrollPack.effective_from <= end).order_by(PayrollPack.effective_from.desc(), PayrollPack.version.desc()).limit(1))
            if pack is None:
                raise ValueError(f"No destination pack reference for {source_run['country_code']} {start}")
            for branch_id in branch_ids:
                run_id = legacy_id("payroll_run_branch", f"{source_run['id']}/{branch_id}")
                self.run_ids[(source_run["id"], branch_id)] = run_id
                exclusions = [self.identity("employees", r["employee_id"]) for r in self.source["payroll_run_exclusions"]
                    if r["payroll_run_id"] == source_run["id"] and self.branch_at(r["employee_id"], end, source_run["country_code"]) == branch_id]
                status = "APPROVED" if source_run["status"] in {"approved", "finance_reviewed", "paid"} else "DRAFT"
                gross_total = deduction_total = net_total = employer_total = D(0)
                for source_slip in split[branch_id]:
                    person = self.people[source_slip["employee_id"]]
                    earning_lines = parsed(source_slip["earnings_breakdown"]) or []
                    deduction_lines = parsed(source_slip["deductions_breakdown"]) or []
                    gross, net = amount(source_slip["gross_pay"]), amount(source_slip["net_pay"])
                    deductions = sum((amount(r["amount"]) for r in deduction_lines), D(0))
                    earnings = sum((amount(r["amount"]) for r in earning_lines), D(0))
                    if earnings != gross or gross - deductions != net:
                        raise ValueError(f"Financial snapshot does not reconcile: payroll item {source_slip['id']}")
                    applicable = [r for r in self.compensations[person["id"]] if r[0] <= end]
                    basic = next((amount(r["amount"]) for r in earning_lines if r.get("code") == "BASIC"), None)
                    if applicable:
                        compensation_id = max(applicable)[1]
                    else:
                        compensation_id = legacy_id("historic_compensation", f"{person['id']}/{start}")
                        if compensation_id not in {r["id"] for r in self.rows["employee_compensation"]}:
                            self.add("employee_compensation", dict(id=compensation_id, company_id=self.company(person["company_id"]),
                                employee_id=self.identity("employees", person["id"]), effective_from=start,
                                structure="GROSS_ONLY", gross_amount=gross, basic_amount=None, currency_id=self.branch_currency[branch_id], is_historical=True))
                    slip_id = self.identity("payroll_items", source_slip["id"])
                    employer = amount(source_slip["nssf_employer"])
                    self.add("payroll_payslips", dict(id=slip_id, company_id=self.company(person["company_id"]), run_id=run_id,
                        employee_id=self.identity("employees", person["id"]), compensation_id=compensation_id,
                        employee_name=" ".join(filter(None, [person["first_name"], person.get("middle_name"), person["last_name"]])),
                        employee_number=person.get("employee_number") or f"LEGACY-{person['id']:04d}", gross=gross, basic=basic,
                        employee_deductions=deductions, employer_contributions=employer, net=net), "payroll_items", source_slip["id"])
                    lines = [("GROSS", "Gross pay", "EARNING", gross, None, None)]
                    for line in earning_lines:
                        code = line.get("code", "EARNING")
                        benefit = int(code[4:]) if code.startswith("BEN-") and code[4:].isdigit() else None
                        lines.append((code, line.get("name") or code, "EARNING", amount(line["amount"]), None,
                            self.maps["employee_benefits"].get(benefit)))
                    for line in deduction_lines:
                        code = line.get("code", "DEDUCTION")
                        deduction = int(code[4:]) if code.startswith("DED_") and code[4:].isdigit() else None
                        code = {"NSSF_TIER1": "NSSF_I", "NSSF_TIER2": "NSSF_II", "HOUSING_LEVY": "HOUSING"}.get(code, code)
                        lines.append((code, line.get("name") or code, "DEDUCTION", amount(line["amount"]),
                            self.maps["employee_deductions"].get(deduction), None))
                    lines.append(("TAXABLE", "Taxable pay", "EARNING", amount(source_slip["taxable_pay"]), None, None))
                    if employer:
                        lines.append(("NSSF_EMPLOYER", "NSSF employer", "EMPLOYER", employer, None, None))
                    for index, (code, name, kind, value, deduction_id, benefit_id) in enumerate(lines):
                        self.add("payroll_payslip_lines", dict(id=legacy_id("payslip_lines", f"{source_slip['id']}/{index}"),
                            company_id=self.company(person["company_id"]), payslip_id=slip_id, code=code,
                            name=name[:100], party="EMPLOYER" if kind == "EMPLOYER" else "EMPLOYEE", kind=kind,
                            amount=value, sort_order=index, employee_deduction_id=deduction_id, employee_benefit_id=benefit_id))
                    gross_total += gross; deduction_total += deductions; net_total += net; employer_total += employer
                    if source_run["status"] == "paid" and net > 0:
                        if not source_run.get("paid_at"):
                            raise ValueError("Paid payroll has no recorded payment date")
                        self.add("payment_records", dict(id=legacy_id("payroll_payment", source_slip["id"]), tenant_id=self.tenant,
                            company_id=self.company(person["company_id"]), payslip_id=slip_id, consultant_pay_id=None, benefit_id=None,
                            period_start=start, currency_id=self.branch_currency[branch_id], recipient_name=f"{person['first_name']} {person['last_name']}",
                            amount=net, paid_on=day(source_run["paid_at"]), method="OTHER", reference=f"LEGACY-PAYROLL-{source_run['id']}-{source_slip['id']}",
                            note=f"Imported paid status; source payment reference: {source_run.get('payment_reference') or 'not specified'}", status="POSTED", recorded_by_id=None))
                self.add("payroll_runs", dict(id=run_id, company_id=self.company(source_run["company_id"]),
                    branch_id=self.identity("branches", branch_id), period_start=start, period_end=end,
                    excluded_employee_ids=[str(r) for r in exclusions], status=status, payroll_pack_id=pack.id,
                    currency_id=self.branch_currency[branch_id], gross_total=gross_total, deduction_total=deduction_total,
                    employer_total=employer_total, net_total=net_total), "payroll_runs", source_run["id"])
        await self.write(session, "employee_compensation")
        await self.write(session, "payroll_runs")
        await self.write(session, "payroll_payslips")
        await self.write(session, "payroll_payslip_lines")

    async def consultant_records(self, session):
        for row in self.source["consultants"]:
            self.add("consultants", dict(id=self.identity("consultants", row["id"]), tenant_id=self.tenant,
                company_id=self.company(row["company_id"]), branch_id=self.identity("branches", row["branch_id"]),
                consultant_number=row.get("consultant_number") or f"LEGACY-C{row['id']}", first_name=row["first_name"],
                last_name=row["last_name"], other_names=row.get("middle_name"), email=row.get("email"), phone=row.get("phone"),
                id_number=row.get("national_id"), pin_number=row.get("kra_pin"), bank_name=row.get("bank_name"),
                bank_branch=row.get("bank_branch"), bank_account_number=row.get("bank_account_number"), bank_code=row.get("bank_code"),
                start_date=row["start_date"], end_date=row.get("end_date"), withholding_rate=row["withholding_rate"],
                prorate_payroll=row["prorate_payroll"], status="ACTIVE" if row["status"] == "active" else "INACTIVE", notes=row.get("notes")), "consultants", row["id"])
        await self.write(session, "consultants")
        for row in self.source["consultant_compensation"]:
            person = self.consultants[row["consultant_id"]]
            self.add("consultant_compensation", dict(id=self.identity("consultant_compensation", row["id"]), tenant_id=self.tenant,
                company_id=self.company(person["company_id"]), consultant_id=self.identity("consultants", person["id"]),
                effective_from=row["effective_from"], effective_to=row.get("effective_to"), monthly_fee=row["monthly_fee"],
                other_allowances=row["other_allowances"], notes=row.get("notes")), "consultant_compensation", row["id"])
        await self.write(session, "consultant_compensation")
        for row in self.source["consultant_payroll_items"]:
            person = self.consultants[row["consultant_id"]]
            source_run = self.runs[row["payroll_run_id"]]
            start = date(source_run["pay_year"], source_run["pay_month"], 1)
            end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
            fees = [r for r in self.source["consultant_compensation"] if r["consultant_id"] == person["id"] and day(r["effective_from"]) <= end]
            if not fees:
                raise ValueError("Consultant history has no matching compensation")
            fee = max(fees, key=lambda r: r["effective_from"])
            gross, withholding, net = amount(row["gross_pay"]), amount(row["withholding_tax"]), amount(row["net_pay"])
            if gross - withholding != net:
                raise ValueError("Consultant financial snapshot does not reconcile")
            identity = self.identity("consultant_payroll_items", row["id"])
            name = " ".join(filter(None, [person["first_name"], person.get("middle_name"), person["last_name"]]))
            from app.services.payroll_calc import salary_days
            paid_days = salary_days(start, end, day(person["start_date"])) if row.get("is_pro_rata") else 30
            self.add("consultant_pay", dict(id=identity, tenant_id=self.tenant, company_id=self.company(person["company_id"]),
                consultant_id=self.identity("consultants", person["id"]), branch_id=self.identity("branches", person["branch_id"]),
                compensation_id=self.identity("consultant_compensation", fee["id"]), period_start=start, period_end=end,
                currency_id=self.branch_currency[person["branch_id"]], recipient_name=name, gross=gross,
                withholding_rate=person["withholding_rate"], withholding_tax=withholding, net=net, payable_days=paid_days,
                status="APPROVED" if source_run["status"] in {"approved", "finance_reviewed", "paid"} else "DRAFT",
                approved_by_id=self.identity("users", source_run.get("approved_by_id")), approved_at=source_run.get("approved_at")), "consultant_payroll_items", row["id"])
            if source_run["status"] == "paid" and net > 0:
                self.add("payment_records", dict(id=legacy_id("consultant_payment", row["id"]), tenant_id=self.tenant,
                    company_id=self.company(person["company_id"]), payslip_id=None, consultant_pay_id=identity, benefit_id=None,
                    period_start=start, currency_id=self.branch_currency[person["branch_id"]], recipient_name=name, amount=net,
                    paid_on=day(source_run["paid_at"]), method="OTHER", reference=f"LEGACY-CONSULTANT-{row['id']}",
                    note="Imported original paid payroll status", status="POSTED", recorded_by_id=None))
        await self.write(session, "consultant_pay")
        benefits = {r["id"]: r for r in self.source["employee_benefits"]}
        for row in self.source["employee_benefit_payments"]:
            if row["status"] != "paid":
                continue
            benefit = benefits[row["benefit_id"]]
            person = self.people[benefit["employee_id"]]
            if not row.get("paid_on"):
                raise ValueError("A paid benefit is missing its payment date")
            self.add("payment_records", dict(id=self.identity("employee_benefit_payments", row["id"]), tenant_id=self.tenant,
                company_id=self.company(person["company_id"]), payslip_id=None, consultant_pay_id=None,
                benefit_id=self.identity("employee_benefits", benefit["id"]), period_start=date(row["period_year"], row["period_month"], 1),
                currency_id=self.branch_currency[person["branch_id"]], recipient_name=f"{person['first_name']} {person['last_name']}",
                amount=amount(row["amount"]), paid_on=row["paid_on"], method="OTHER", reference=f"LEGACY-BENEFIT-{row['id']}",
                note=row.get("notes") or "Imported original benefit payment", status="POSTED", recorded_by_id=None), "employee_benefit_payments", row["id"])
        await self.write(session, "payment_records")

    async def overtime(self, session):
        for row in self.source["overtime_requests"]:
            person = self.people[row["employee_id"]]
            month = date(row["for_pay_year"], row["for_pay_month"], 1)
            end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
            salaries = [r for r in self.rows["employee_compensation"] if r["employee_id"] == self.identity("employees", person["id"])
                and not r.get("is_historical") and day(r["effective_from"]) <= end]
            if row["status"] not in {"cancelled", "rejected"}:
                raise ValueError("Non-closed source overtime requires an agreed rate before import")
            dates = [value.strip() for value in row["worked_dates"].split(",") if value.strip()]
            entry = dict(id=self.identity("overtime_requests", row["id"]), tenant_id=self.tenant,
                company_id=self.company(person["company_id"]), employee_id=self.identity("employees", person["id"]),
                branch_id=self.identity("branches", person["branch_id"]), currency_id=self.branch_currency[person["branch_id"]],
                worked_dates=dates, days=row["days"], daily_rate=None, amount=None, payroll_month=month,
                reason=row.get("reason"), status=row["status"].upper(), submitted_by_id=self.identity("users", row.get("submitted_by_user_id")),
                reviewed_by_id=self.identity("users", row.get("reviewed_by_user_id")), reviewed_at=row.get("reviewed_at"),
                review_notes=(row.get("review_notes") or "") + " [Imported: source did not store a rate or payable amount.]",
                employee_benefit_id=None)
            self.add("overtime_requests", entry, "overtime_requests", row["id"])
        await self.write(session, "overtime_requests")
        for row in self.source["employee_assignment_history"]:
            person = self.people[row["employee_id"]]
            self.add("employee_lifecycle_events", dict(id=self.identity("employee_assignment_history", row["id"]),
                company_id=self.company(person["company_id"]), employee_id=self.identity("employees", person["id"]),
                event_type="ROLE_CHANGE", reason="Legacy assignment history", effective_on=row["effective_from"], note=row.get("change_reason"),
                to_department_id=self.identity("departments", row.get("department_id")), to_job_title_id=self.identity("job_titles", row.get("job_title_id")),
                to_branch_id=self.identity("branches", row.get("branch_id")), created_by=self.identity("users", row.get("created_by_id")),
                created_at=row["created_at"]), "employee_assignment_history", row["id"])
        await self.write(session, "employee_lifecycle_events")

    async def archive(self, session):
        user_companies = {r["id"]: r.get("company_id") for r in self.source["users"]}
        for table, rows in self.source.items():
            for row in rows:
                source_id = row.get("id")
                if source_id is None:
                    source_id = "/".join(str(row[key]) for key in sorted(row) if key.endswith("_id"))
                source_company = row.get("company_id")
                if source_company is None and row.get("employee_id") in self.people:
                    source_company = self.people[row["employee_id"]]["company_id"]
                if source_company is None and row.get("consultant_id") in self.consultants:
                    source_company = self.consultants[row["consultant_id"]]["company_id"]
                if source_company is None and row.get("user_id"):
                    source_company = user_companies.get(row["user_id"])
                destinations = self.destinations.get((table, source_id), [])
                if not destinations and source_id in self.maps.get(table, {}):
                    destinations = [(table, self.maps[table][source_id])]
                self.add("legacy_import_records", dict(id=legacy_id("archive", f"{table}/{source_id}"),
                    tenant_id=self.tenant, company_id=self.company(source_company) if source_company else None,
                    source=self.snapshot["source"], source_table=table, source_id=str(source_id),
                    destination_table=destinations[0][0] if destinations else None,
                    destination_ids=[str(r[1]) for r in destinations], payload=scrub(row), snapshot_sha256=self.fingerprint))
        await self.write(session, "legacy_import_records")


async def main(args):
    raw = Path(args.snapshot).read_bytes()
    snapshot, mapping = json.loads(raw), json.loads(Path(args.mapping).read_text())
    fingerprint = hashlib.sha256(raw).hexdigest()
    url = make_url(get_settings().database_url)
    if args.database:
        if not args.database.startswith("hrms_migration_"):
            raise ValueError("Database overrides must be isolated hrms_migration_* rehearsal databases")
        url = url.set(database=args.database)
    engine = create_async_engine(url, hide_parameters=True, connect_args={"server_settings": {"timezone": "UTC"}})
    report = {}
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            async with session.begin():
                await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
                await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('legacy-hrms-data-import', 0))"))
                imported = (await session.scalars(select(LegacyImportRecord.snapshot_sha256).distinct())).all()
                if imported:
                    if set(imported) == {fingerprint}:
                        print("This exact snapshot was already imported; no changes made.")
                        return
                    raise ValueError("A different snapshot was previously imported; refusing an automatic overwrite")
                owner_id = uuid.UUID(mapping["preserved_owner_id"])
                owner = await session.get(User, owner_id)
                owner_before = (owner.id, owner.email, owner.password_hash, owner.role, owner.tenant_id)
                importer = Importer(snapshot, mapping, fingerprint, args.uploads_root)
                await importer.prepare(session)
                await session.refresh(owner)
                if owner_before != (owner.id, owner.email, owner.password_hash, owner.role, owner.tenant_id):
                    raise ValueError("Existing owner identity changed unexpectedly")
                report = dict(mode="APPLY" if args.apply else "ROLLBACK_REHEARSAL", snapshot_sha256=fingerprint,
                    source_captured_at=snapshot["captured_at"], source_counts={key: len(rows) for key, rows in snapshot["tables"].items()},
                    destination_counts={key: len(rows) for key, rows in importer.rows.items()},
                    preserved_owner=True, leave_balance_checks=importer.balance_checks, warnings=importer.warnings)
                report["referenced_files_copied"] = importer.files_copied
                report["financial_reconciliation"] = "All employee and consultant earning/deduction/net snapshots reconciled exactly"
                if not args.apply:
                    await session.rollback()
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key not in {"leave_balance_checks"}}, indent=2, default=str))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--database")
    parser.add_argument("--report")
    parser.add_argument("--uploads-root")
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
