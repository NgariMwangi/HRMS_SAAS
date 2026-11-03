"""document type category

Revision ID: 018_document_type_category
Revises: 017_employee_documents
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_document_type_category"
down_revision: Union[str, Sequence[str], None] = "017_employee_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_types",
        sa.Column("category", sa.String(length=30), nullable=False, server_default="PERSONAL"),
    )
    op.drop_constraint("uq_document_type_name", "document_types", type_="unique")
    op.create_unique_constraint(
        "uq_document_type_category_name",
        "document_types",
        ["company_id", "category", "name"],
    )
    op.create_index("ix_document_types_category", "document_types", ["company_id", "category"])


def downgrade() -> None:
    op.drop_index("ix_document_types_category", table_name="document_types")
    op.drop_constraint("uq_document_type_category_name", "document_types", type_="unique")
    op.create_unique_constraint("uq_document_type_name", "document_types", ["company_id", "name"])
    op.drop_column("document_types", "category")
