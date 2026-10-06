import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDPrimaryKeyMixin, Base


class AIGenerationLog(UUIDPrimaryKeyMixin, Base):
    """One AI draft and its later approval.

    suggested_reply is the original model text and is never updated.
    edited_reply is the agent's wording. final_reply is the text that was
    sent. A row becomes SENT only through the send endpoint.
    """

    __tablename__ = "ai_generation_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "brand_id"],
            ["conversations.id", "conversations.brand_id"],
            name="fk_ai_generation_logs_conversation_brand",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_message_id", "conversation_id", "message_author_type"],
            ["messages.id", "messages.conversation_id", "messages.author_type"],
            name="fk_ai_generation_logs_customer_message",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "message_author_type = 'CUSTOMER'",
            name="ck_ai_generation_logs_customer_message",
        ),
        CheckConstraint(
            "evidence_status IN ('SUPPORTED', 'PARTIALLY_SUPPORTED', 'INSUFFICIENT_INFORMATION', 'HUMAN_REVIEW_REQUIRED')",
            name="ck_ai_generation_logs_evidence_status",
        ),
        CheckConstraint(
            "char_length(btrim(suggested_reply)) > 0",
            name="ck_ai_generation_logs_suggested_reply_not_blank",
        ),
        CheckConstraint(
            "model_name IS NULL OR char_length(btrim(model_name)) > 0",
            name="ck_ai_generation_logs_model_name",
        ),
        CheckConstraint(
            "error_detail IS NULL OR char_length(btrim(error_detail)) > 0",
            name="ck_ai_generation_logs_error_detail",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_ai_generation_logs_latency_ms",
        ),
        CheckConstraint(
            "prompt_tokens IS NULL OR prompt_tokens >= 0",
            name="ck_ai_generation_logs_prompt_tokens",
        ),
        CheckConstraint(
            "completion_tokens IS NULL OR completion_tokens >= 0",
            name="ck_ai_generation_logs_completion_tokens",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_ai_generation_logs_total_tokens",
        ),
        CheckConstraint(
            "status IN ('AI_GENERATED', 'EDITED', 'APPROVED', 'SENT')",
            name="ck_ai_generation_logs_status",
        ),
        CheckConstraint(
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
            name="ck_ai_generation_logs_status_payload",
        ),
        ForeignKeyConstraint(
            ["sent_message_id", "conversation_id", "sent_author_type"],
            ["messages.id", "messages.conversation_id", "messages.author_type"],
            name="fk_ai_generation_logs_sent_message",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("sent_message_id", name="uq_ai_generation_logs_sent_message"),
        Index("ix_ai_generation_logs_conversation_created", "conversation_id", "created_at"),
        Index("ix_ai_generation_logs_customer_message_id", "customer_message_id"),
        Index("ix_ai_generation_logs_brand_id", "brand_id"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", name="fk_ai_generation_logs_brand_id", ondelete="RESTRICT"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    customer_message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    message_author_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'CUSTOMER'"),
    )
    suggested_reply: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_status: Mapped[str] = mapped_column(String(32), nullable=False)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_knowledge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    retrieved_context: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'AI_GENERATED'"),
    )
    edited_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    sent_author_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    brand: Mapped["Brand"] = relationship(
        back_populates="ai_generation_logs",
        foreign_keys=[brand_id],
    )
    conversation: Mapped["Conversation"] = relationship(
        back_populates="ai_generation_logs",
        foreign_keys=[conversation_id, brand_id],
        overlaps="brand",
    )
    customer_message: Mapped["Message"] = relationship(
        back_populates="ai_generation_logs",
        foreign_keys=[customer_message_id, conversation_id, message_author_type],
        overlaps="conversation",
    )
