"""add knowledge full-text search vector

Revision ID: f3a9c2d81e47
Revises: d4f6a1c87b31
Create Date: 2026-10-06 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "f3a9c2d81e47"
down_revision: Union[str, Sequence[str], None] = "d4f6a1c87b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE knowledge_base_entries
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english', title || ' ' || content)
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_base_entries_search
        ON knowledge_base_entries
        USING GIN (search_vector)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_base_entries_search")
    op.drop_column("knowledge_base_entries", "search_vector")
