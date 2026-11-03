"""drop document types; keep category on employee documents

Revision ID: 019_drop_document_types
Revises: 018_document_type_category
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_drop_document_types"
down_revision: Union[str, Sequence[str], None] = "018_document_type_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employee_documents",
        sa.Column("category", sa.String(length=30), nullable=True),
    )
    op.execute(
        """
        UPDATE employee_documents AS documents
        SET category = types.category
        FROM document_types AS types
        WHERE documents.document_type_id = types.id
        """
    )
    op.execute("UPDATE employee_documents SET category = 'PERSONAL' WHERE category IS NULL")
    op.alter_column("employee_documents", "category", existing_type=sa.String(length=30), nullable=False)
    op.create_index("ix_employee_documents_category", "employee_documents", ["company_id", "category"])
    inspector = sa.inspect(op.get_bind())
    for index in inspector.get_indexes("employee_documents"):
        if index.get("name") == "ix_employee_documents_document_type_id":
            op.drop_index(index["name"], table_name="employee_documents")
    for fk in inspector.get_foreign_keys("employee_documents"):
        if "document_type_id" in fk.get("constrained_columns", []):
            op.drop_constraint(fk["name"], "employee_documents", type_="foreignkey")
    op.drop_column("employee_documents", "document_type_id")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_document_types ON document_types")
    op.drop_table("document_types")


def downgrade() -> None:
    raise NotImplementedError("document types were removed in favor of category")
