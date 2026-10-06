"""reshape knowledge base entries

Revision ID: c3a8e91b4f20
Revises: 28771d38c25c
Create Date: 2026-10-06 13:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a8e91b4f20"
down_revision: Union[str, Sequence[str], None] = "28771d38c25c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_knowledge_body_not_blank",
        "knowledge_base_entries",
        type_="check",
    )
    op.alter_column("knowledge_base_entries", "body", new_column_name="content")
    op.create_check_constraint(
        "ck_knowledge_content_not_blank",
        "knowledge_base_entries",
        "char_length(btrim(content)) > 0",
    )
    op.add_column(
        "knowledge_base_entries",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        """
        UPDATE knowledge_base_entries
        SET category = CASE category
            WHEN 'return_policy' THEN 'RETURN'
            WHEN 'refund_policy' THEN 'REFUND'
            WHEN 'shipping_policy' THEN 'SHIPPING'
            WHEN 'cancellation_policy' THEN 'CANCELLATION'
            ELSE category
        END
        """
    )
    op.drop_constraint(
        "uq_knowledge_brand_category",
        "knowledge_base_entries",
        type_="unique",
    )
    op.create_check_constraint(
        "ck_knowledge_category",
        "knowledge_base_entries",
        "category IN ('RETURN', 'REFUND', 'SHIPPING', 'CANCELLATION')",
    )
    op.create_index(
        "ix_knowledge_base_entries_brand_id",
        "knowledge_base_entries",
        ["brand_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_base_entries_brand_id",
        table_name="knowledge_base_entries",
    )
    op.drop_constraint("ck_knowledge_category", "knowledge_base_entries", type_="check")
    op.execute(
        """
        UPDATE knowledge_base_entries
        SET category = CASE category
            WHEN 'RETURN' THEN 'return_policy'
            WHEN 'REFUND' THEN 'refund_policy'
            WHEN 'SHIPPING' THEN 'shipping_policy'
            WHEN 'CANCELLATION' THEN 'cancellation_policy'
            ELSE category
        END
        """
    )
    op.create_unique_constraint(
        "uq_knowledge_brand_category",
        "knowledge_base_entries",
        ["brand_id", "category"],
    )
    op.drop_column("knowledge_base_entries", "active")
    op.drop_constraint(
        "ck_knowledge_content_not_blank",
        "knowledge_base_entries",
        type_="check",
    )
    op.alter_column("knowledge_base_entries", "content", new_column_name="body")
    op.create_check_constraint(
        "ck_knowledge_body_not_blank",
        "knowledge_base_entries",
        "char_length(btrim(body)) > 0",
    )
