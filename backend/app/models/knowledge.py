import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDPrimaryKeyMixin, Base, TimestampMixin, value_enum
from app.models.enums import KnowledgeCategory


class KnowledgeBaseEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_base_entries"
    __table_args__ = (
        CheckConstraint("char_length(btrim(title)) > 0", name="ck_knowledge_title_not_blank"),
        CheckConstraint(
            "char_length(btrim(content)) > 0",
            name="ck_knowledge_content_not_blank",
        ),
        CheckConstraint(
            "category IN ('RETURN', 'REFUND', 'SHIPPING', 'CANCELLATION')",
            name="ck_knowledge_category",
        ),
        Index("ix_knowledge_base_entries_brand_id", "brand_id"),
        Index(
            "ix_knowledge_base_entries_search",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", name="fk_knowledge_brand_id", ondelete="RESTRICT"),
        nullable=False,
    )
    category: Mapped[KnowledgeCategory] = mapped_column(
        value_enum(KnowledgeCategory, "knowledge_category"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', title || ' ' || content)",
            persisted=True,
        ),
        nullable=False,
    )

    brand: Mapped["Brand"] = relationship(back_populates="knowledge_entries")
