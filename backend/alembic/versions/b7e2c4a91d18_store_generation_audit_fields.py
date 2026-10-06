"""store generation audit fields

Revision ID: b7e2c4a91d18
Revises: a9d4c2e81f06
Create Date: 2026-10-06 16:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c4a91d18"
down_revision: Union[str, Sequence[str], None] = "a9d4c2e81f06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_generation_logs", sa.Column("error_detail", sa.Text(), nullable=True))
    op.add_column(
        "ai_generation_logs",
        sa.Column("retrieved_context", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("ai_generation_logs", sa.Column("model_name", sa.String(length=120), nullable=True))
    op.add_column("ai_generation_logs", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("ai_generation_logs", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_generation_logs", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_generation_logs", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_ai_generation_logs_model_name",
        "ai_generation_logs",
        "model_name IS NULL OR char_length(btrim(model_name)) > 0",
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_error_detail",
        "ai_generation_logs",
        "error_detail IS NULL OR char_length(btrim(error_detail)) > 0",
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_latency_ms",
        "ai_generation_logs",
        "latency_ms IS NULL OR latency_ms >= 0",
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_prompt_tokens",
        "ai_generation_logs",
        "prompt_tokens IS NULL OR prompt_tokens >= 0",
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_completion_tokens",
        "ai_generation_logs",
        "completion_tokens IS NULL OR completion_tokens >= 0",
    )
    op.create_check_constraint(
        "ck_ai_generation_logs_total_tokens",
        "ai_generation_logs",
        "total_tokens IS NULL OR total_tokens >= 0",
    )


def downgrade() -> None:
    for name in (
        "ck_ai_generation_logs_total_tokens",
        "ck_ai_generation_logs_completion_tokens",
        "ck_ai_generation_logs_prompt_tokens",
        "ck_ai_generation_logs_latency_ms",
        "ck_ai_generation_logs_error_detail",
        "ck_ai_generation_logs_model_name",
    ):
        op.drop_constraint(name, "ai_generation_logs", type_="check")
    op.drop_column("ai_generation_logs", "total_tokens")
    op.drop_column("ai_generation_logs", "completion_tokens")
    op.drop_column("ai_generation_logs", "prompt_tokens")
    op.drop_column("ai_generation_logs", "latency_ms")
    op.drop_column("ai_generation_logs", "model_name")
    op.drop_column("ai_generation_logs", "retrieved_context")
    op.drop_column("ai_generation_logs", "error_detail")
