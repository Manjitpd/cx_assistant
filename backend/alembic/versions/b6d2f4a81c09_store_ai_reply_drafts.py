"""store AI reply drafts

Revision ID: b6d2f4a81c09
Revises: f3a9c2d81e47
Create Date: 2026-10-06 14:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6d2f4a81c09"
down_revision: Union[str, Sequence[str], None] = "f3a9c2d81e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_generation_logs", sa.Column("suggested_reply", sa.Text(), nullable=False))
    op.add_column("ai_generation_logs", sa.Column("evidence_status", sa.String(length=32), nullable=False))
    op.add_column("ai_generation_logs", sa.Column("warning", sa.Text(), nullable=True))
    op.add_column(
        "ai_generation_logs",
        sa.Column("retrieved_knowledge_ids", sa.JSON(), nullable=False),
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_evidence_status",
        "ai_generation_logs",
        "evidence_status IN ('supported', 'needs_review')",
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_suggested_reply_not_blank",
        "ai_generation_logs",
        "char_length(btrim(suggested_reply)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ai_generation_logs_suggested_reply_not_blank",
        "ai_generation_logs",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_generation_logs_evidence_status",
        "ai_generation_logs",
        type_="check",
    )
    op.drop_column("ai_generation_logs", "retrieved_knowledge_ids")
    op.drop_column("ai_generation_logs", "warning")
    op.drop_column("ai_generation_logs", "evidence_status")
    op.drop_column("ai_generation_logs", "suggested_reply")
