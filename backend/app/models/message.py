import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDPrimaryKeyMixin, Base, TimestampMixin, value_enum
from app.models.enums import MessageAuthor


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "conversation_id",
            "author_type",
            name="uq_messages_id_conversation_author",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "brand_id"],
            ["conversations.id", "conversations.brand_id"],
            name="fk_messages_conversation_brand",
            ondelete="RESTRICT",
        ),
        CheckConstraint("char_length(btrim(body)) > 0", name="ck_messages_body_not_blank"),
        CheckConstraint(
            "author_type IN ('CUSTOMER', 'AGENT')",
            name="ck_messages_author_type",
        ),
        CheckConstraint(
            "idempotency_key IS NULL OR char_length(btrim(idempotency_key)) > 0",
            name="ck_messages_idempotency_key_not_blank",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_brand_id", "brand_id"),
        Index(
            "uq_messages_conversation_idempotency",
            "conversation_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", name="fk_messages_brand_id", ondelete="RESTRICT"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    author_type: Mapped[MessageAuthor] = mapped_column(
        value_enum(MessageAuthor, "message_author"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)

    brand: Mapped["Brand"] = relationship(
        back_populates="messages",
        foreign_keys=[brand_id],
        overlaps="messages",
    )
    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
        foreign_keys=[conversation_id, brand_id],
        overlaps="brand,messages",
    )
    ai_generation_logs: Mapped[list["AIGenerationLog"]] = relationship(
        back_populates="customer_message",
        foreign_keys="AIGenerationLog.customer_message_id",
    )
