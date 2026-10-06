"""use uppercase message authors

Revision ID: d4f6a1c87b31
Revises: c3a8e91b4f20
Create Date: 2026-10-06 13:25:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "d4f6a1c87b31"
down_revision: Union[str, Sequence[str], None] = "c3a8e91b4f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE messages
        SET author_type = CASE author_type
            WHEN 'customer' THEN 'CUSTOMER'
            WHEN 'agent' THEN 'AGENT'
            ELSE author_type
        END
        """
    )
    op.create_check_constraint(
        "ck_messages_author_type",
        "messages",
        "author_type IN ('CUSTOMER', 'AGENT')",
    )
    op.drop_constraint(
        "ck_ai_generation_logs_customer_message",
        "ai_generation_logs",
        type_="check",
    )
    op.execute(
        "ALTER TABLE ai_generation_logs ALTER COLUMN message_author_type SET DEFAULT 'CUSTOMER'"
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_customer_message",
        "ai_generation_logs",
        "message_author_type = 'CUSTOMER'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ai_generation_logs_customer_message",
        "ai_generation_logs",
        type_="check",
    )
    op.execute(
        "ALTER TABLE ai_generation_logs ALTER COLUMN message_author_type SET DEFAULT 'customer'"
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_customer_message",
        "ai_generation_logs",
        "message_author_type = 'customer'",
    )
    op.drop_constraint("ck_messages_author_type", "messages", type_="check")
    op.execute(
        """
        UPDATE messages
        SET author_type = CASE author_type
            WHEN 'CUSTOMER' THEN 'customer'
            WHEN 'AGENT' THEN 'agent'
            ELSE author_type
        END
        """
    )
