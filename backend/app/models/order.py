import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDPrimaryKeyMixin, Base, TimestampMixin, value_enum
from app.models.enums import OrderStatus


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("id", "brand_id", name="uq_orders_id_brand"),
        UniqueConstraint("id", "customer_id", "brand_id", name="uq_orders_id_customer_brand"),
        UniqueConstraint("brand_id", "order_number", name="uq_orders_brand_order_number"),
        ForeignKeyConstraint(
            ["customer_id", "brand_id"],
            ["customers.id", "customers.brand_id"],
            name="fk_orders_customer_brand",
            ondelete="RESTRICT",
        ),
        CheckConstraint("total_cents >= 0", name="ck_orders_total_cents_nonnegative"),
        CheckConstraint(
            "char_length(btrim(order_number)) > 0",
            name="ck_orders_order_number_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(product_name)) > 0",
            name="ck_orders_product_name_not_blank",
        ),
        CheckConstraint(
            "currency = upper(currency) AND char_length(currency) = 3",
            name="ck_orders_currency_code",
        ),
        Index("ix_orders_customer_id", "customer_id"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", name="fk_orders_brand_id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        value_enum(OrderStatus, "order_status"),
        nullable=False,
        server_default=text("'pending'"),
    )
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'USD'"))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    brand: Mapped["Brand"] = relationship(
        back_populates="orders",
        foreign_keys=[brand_id],
        overlaps="orders",
    )
    customer: Mapped["Customer"] = relationship(
        back_populates="orders",
        foreign_keys=[customer_id, brand_id],
        overlaps="brand,orders",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="order",
        overlaps="brand,conversations",
    )
