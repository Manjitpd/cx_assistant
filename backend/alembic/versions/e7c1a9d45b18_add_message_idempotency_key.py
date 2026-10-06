"""add message idempotency key

Revision ID: e7c1a9d45b18
Revises: c4e8a1b72d30
Create Date: 2026-10-06 14:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7c1a9d45b18"
down_revision: Union[str, Sequence[str], None] = "c4e8a1b72d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("idempotency_key", sa.String(length=80), nullable=True))
    op.create_check_constraint(
        "ck_messages_idempotency_key_not_blank",
        "messages",
        "idempotency_key IS NULL OR char_length(btrim(idempotency_key)) > 0",
    )
    op.create_index(
        "uq_messages_conversation_idempotency",
        "messages",
        ["conversation_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_conversation_idempotency", table_name="messages")
    op.drop_constraint("ck_messages_idempotency_key_not_blank", "messages", type_="check")
    op.drop_column("messages", "idempotency_key")
