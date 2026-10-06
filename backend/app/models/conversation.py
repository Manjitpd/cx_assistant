import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDPrimaryKeyMixin, Base, TimestampMixin, value_enum
from app.models.enums import ConversationStatus


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("id", "brand_id", name="uq_conversations_id_brand"),
        ForeignKeyConstraint(
            ["customer_id", "brand_id"],
            ["customers.id", "customers.brand_id"],
            name="fk_conversations_customer_brand",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["order_id", "customer_id", "brand_id"],
            ["orders.id", "orders.customer_id", "orders.brand_id"],
            name="fk_conversations_order_customer_brand",
            ondelete="RESTRICT",
        ),
        CheckConstraint("char_length(btrim(subject)) > 0", name="ck_conversations_subject_not_blank"),
        Index("ix_conversations_brand_status", "brand_id", "status"),
        Index("ix_conversations_customer_id", "customer_id"),
        Index("ix_conversations_order_id", "order_id"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", name="fk_conversations_brand_id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        value_enum(ConversationStatus, "conversation_status"),
        nullable=False,
        server_default=ConversationStatus.OPEN.value,
    )

    brand: Mapped["Brand"] = relationship(
        back_populates="conversations",
        foreign_keys=[brand_id],
    )
    customer: Mapped["Customer"] = relationship(
        back_populates="conversations",
        foreign_keys=[customer_id, brand_id],
        overlaps="brand,conversations",
    )
    order: Mapped["Order"] = relationship(
        back_populates="conversations",
        foreign_keys=[order_id, customer_id, brand_id],
        overlaps="brand,customer,conversations",
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        overlaps="messages",
        order_by="Message.created_at",
    )
    ai_generation_logs: Mapped[list["AIGenerationLog"]] = relationship(
        back_populates="conversation",
        overlaps="ai_generation_logs,brand,customer_message",
    )
