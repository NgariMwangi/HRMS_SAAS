"""company document categories; lifecycle is locked

Revision ID: 020_document_categories
Revises: 019_drop_document_types
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020_document_categories"
down_revision: Union[str, Sequence[str], None] = "019_drop_document_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMPANY_SCOPE = """
                current_setting('app.is_platform_admin', true) = 'true'
                OR company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
"""


def upgrade() -> None:
    op.create_table(
        "document_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("system_key", sa.String(length=30), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "name", name="uq_document_category_name"),
    )
    op.create_index("ix_document_categories_company_id", "document_categories", ["company_id"])
    op.create_index(
        "uq_document_category_system_key",
        "document_categories",
        ["company_id", "system_key"],
        unique=True,
        postgresql_where=sa.text("system_key IS NOT NULL"),
    )
    op.execute("ALTER TABLE document_categories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_categories FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_document_categories ON document_categories
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )
    op.execute(
        """
        INSERT INTO document_categories (id, company_id, name, system_key, locked, sort_order)
        SELECT gen_random_uuid(), companies.id, seed.name, seed.system_key, seed.locked, seed.sort_order
        FROM companies
        CROSS JOIN (
            VALUES
                ('Personal', 'PERSONAL', false, 10),
                ('Academic', 'ACADEMIC', false, 20),
                ('Work related', 'WORK', false, 30),
                ('Performance related', 'PERFORMANCE', false, 40),
                ('Lifecycle', 'LIFECYCLE', true, 50)
        ) AS seed(name, system_key, locked, sort_order)
        """
    )
    op.add_column("employee_documents", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE employee_documents AS documents
        SET category_id = categories.id
        FROM document_categories AS categories
        WHERE categories.company_id = documents.company_id
          AND categories.system_key = documents.category
        """
    )
    op.execute(
        """
        UPDATE employee_documents AS documents
        SET category_id = categories.id
        FROM document_categories AS categories
        WHERE documents.category_id IS NULL
          AND categories.company_id = documents.company_id
          AND categories.system_key = 'PERSONAL'
        """
    )
    op.alter_column("employee_documents", "category_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(
        "employee_documents_category_id_fkey",
        "employee_documents",
        "document_categories",
        ["category_id"],
        ["id"],
    )
    op.create_index("ix_employee_documents_category_id", "employee_documents", ["category_id"])
    op.drop_index("ix_employee_documents_category", table_name="employee_documents")
    op.drop_column("employee_documents", "category")


def downgrade() -> None:
    raise NotImplementedError("document categories replace the fixed category list")
