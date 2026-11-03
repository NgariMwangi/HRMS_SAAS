"""company document types and employee documents

Revision ID: 017_employee_documents
Revises: 016_employee_next_of_kin
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_employee_documents"
down_revision: Union[str, Sequence[str], None] = "016_employee_next_of_kin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMPANY_SCOPE = """
                current_setting('app.is_platform_admin', true) = 'true'
                OR company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
"""


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = '{table}'
                  AND policyname = 'tenant_isolation_{table}'
            ) THEN
                CREATE POLICY tenant_isolation_{table} ON {table}
                    USING ({_COMPANY_SCOPE})
                    WITH CHECK ({_COMPANY_SCOPE});
            END IF;
        END
        $$;
        """
    )


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    # Two alembic processes (container CMD + a second exec) can race CREATE TABLE;
    # Postgres then fails on the composite type name, not "relation already exists".
    op.execute(sa.text("SELECT pg_advisory_xact_lock(8170017)"))

    if not _has_table("document_types"):
        op.execute(sa.text("DROP TYPE IF EXISTS document_types"))
        op.create_table(
            "document_types",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("requires_expiry", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("company_id", "name", name="uq_document_type_name"),
        )
    if _has_table("document_types") and not _has_index("document_types", "ix_document_types_company_id"):
        op.create_index("ix_document_types_company_id", "document_types", ["company_id"])

    if not _has_table("employee_documents"):
        op.execute(sa.text("DROP TYPE IF EXISTS employee_documents"))
        op.create_table(
            "employee_documents",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("document_type_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("file_bytes", sa.LargeBinary(), nullable=False),
            sa.Column("issued_on", sa.Date(), nullable=True),
            sa.Column("expires_on", sa.Date(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["document_type_id"], ["document_types.id"]),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        )
    if _has_table("employee_documents"):
        for index, cols in (
            ("ix_employee_documents_company_id", ["company_id"]),
            ("ix_employee_documents_employee_id", ["employee_id"]),
            ("ix_employee_documents_document_type_id", ["document_type_id"]),
        ):
            if not _has_index("employee_documents", index):
                op.create_index(index, "employee_documents", cols)

    _rls("document_types")
    _rls("employee_documents")


def downgrade() -> None:
    for table in ("employee_documents", "document_types"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("employee_documents")
    op.drop_table("document_types")
