"""add reply guardrail statuses

Revision ID: a9d4c2e81f06
Revises: e7c1a9d45b18
Create Date: 2026-10-06 15:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9d4c2e81f06"
down_revision: Union[str, Sequence[str], None] = "e7c1a9d45b18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_ai_generation_logs_evidence_status", "ai_generation_logs", type_="check")
    op.execute(
        "UPDATE ai_generation_logs SET evidence_status = 'SUPPORTED' WHERE evidence_status = 'supported'"
    )
    op.execute(
        "UPDATE ai_generation_logs SET evidence_status = 'HUMAN_REVIEW_REQUIRED' "
        "WHERE evidence_status = 'needs_review'"
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_evidence_status",
        "ai_generation_logs",
        "evidence_status IN ("
        "'SUPPORTED', 'PARTIALLY_SUPPORTED', 'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_generation_logs_evidence_status", "ai_generation_logs", type_="check")
    op.execute(
        "UPDATE ai_generation_logs SET evidence_status = 'supported' WHERE evidence_status = 'SUPPORTED'"
    )
    op.execute(
        "UPDATE ai_generation_logs SET evidence_status = 'needs_review' "
        "WHERE evidence_status IN ("
        "'PARTIALLY_SUPPORTED', 'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED'"
        ")"
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_evidence_status",
        "ai_generation_logs",
        "evidence_status IN ('supported', 'needs_review')",
    )
    op.drop_column("orders", "delivered_at")
