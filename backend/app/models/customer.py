import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDPrimaryKeyMixin, Base, TimestampMixin


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("id", "brand_id", name="uq_customers_id_brand"),
        UniqueConstraint("brand_id", "email", name="uq_customers_brand_email"),
        CheckConstraint("char_length(btrim(full_name)) > 0", name="ck_customers_name_not_blank"),
        CheckConstraint(
            "email = lower(email) AND position('@' in email) > 1",
            name="ck_customers_email_format",
        ),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", name="fk_customers_brand_id", ondelete="RESTRICT"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)

    brand: Mapped["Brand"] = relationship(back_populates="customers")
    orders: Mapped[list["Order"]] = relationship(
        back_populates="customer",
        overlaps="orders",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="customer",
        overlaps="brand,conversations",
    )
