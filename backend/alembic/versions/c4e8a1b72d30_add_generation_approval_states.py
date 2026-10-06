"""add generation approval states

Revision ID: c4e8a1b72d30
Revises: b6d2f4a81c09
Create Date: 2026-10-06 14:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a1b72d30"
down_revision: Union[str, Sequence[str], None] = "b6d2f4a81c09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_generation_logs",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'AI_GENERATED'"),
        ),
    )
    op.add_column("ai_generation_logs", sa.Column("edited_reply", sa.Text(), nullable=True))
    op.add_column("ai_generation_logs", sa.Column("final_reply", sa.Text(), nullable=True))
    op.add_column(
        "ai_generation_logs",
        sa.Column("sent_message_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "ai_generation_logs",
        sa.Column("sent_author_type", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_status",
        "ai_generation_logs",
        "status IN ('AI_GENERATED', 'EDITED', 'APPROVED', 'SENT')",
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_status_payload",
        "ai_generation_logs",
        """
        (
            status = 'AI_GENERATED'
            AND edited_reply IS NULL
            AND final_reply IS NULL
            AND sent_message_id IS NULL
            AND sent_author_type IS NULL
        )
        OR (
            status = 'EDITED'
            AND char_length(btrim(edited_reply)) > 0
            AND final_reply IS NULL
            AND sent_message_id IS NULL
            AND sent_author_type IS NULL
        )
        OR (
            status = 'APPROVED'
            AND final_reply IS NULL
            AND sent_message_id IS NULL
            AND sent_author_type IS NULL
            AND (edited_reply IS NULL OR char_length(btrim(edited_reply)) > 0)
        )
        OR (
            status = 'SENT'
            AND sent_message_id IS NOT NULL
            AND sent_author_type = 'AGENT'
            AND char_length(btrim(final_reply)) > 0
        )
        """,
    )
    op.create_foreign_key(
        "fk_ai_generation_logs_sent_message",
        "ai_generation_logs",
        "messages",
        ["sent_message_id", "conversation_id", "sent_author_type"],
        ["id", "conversation_id", "author_type"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_ai_generation_logs_sent_message",
        "ai_generation_logs",
        ["sent_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_ai_generation_logs_sent_message", "ai_generation_logs", type_="unique")
    op.drop_constraint(
        "fk_ai_generation_logs_sent_message",
        "ai_generation_logs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_ai_generation_logs_status_payload",
        "ai_generation_logs",
        type_="check",
    )
    op.drop_constraint("ck_ai_generation_logs_status", "ai_generation_logs", type_="check")
    op.drop_column("ai_generation_logs", "sent_author_type")
    op.drop_column("ai_generation_logs", "sent_message_id")
    op.drop_column("ai_generation_logs", "final_reply")
    op.drop_column("ai_generation_logs", "edited_reply")
    op.drop_column("ai_generation_logs", "status")
