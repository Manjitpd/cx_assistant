from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDPrimaryKeyMixin, Base, TimestampMixin


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_brands_name_not_blank"),
        CheckConstraint(
            "slug = lower(slug) AND slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_brands_slug_format",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)

    customers: Mapped[list["Customer"]] = relationship(back_populates="brand")
    orders: Mapped[list["Order"]] = relationship(back_populates="brand")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="brand")
    messages: Mapped[list["Message"]] = relationship(back_populates="brand")
    knowledge_entries: Mapped[list["KnowledgeBaseEntry"]] = relationship(
        back_populates="brand"
    )
    ai_generation_logs: Mapped[list["AIGenerationLog"]] = relationship(
        back_populates="brand",
        overlaps="conversation",
    )
