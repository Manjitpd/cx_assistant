from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import KnowledgeCategory


class KnowledgeWrite(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: KnowledgeCategory
    content: str = Field(min_length=1)
    active: bool = True
    brand_id: UUID | None = None

    @field_validator("title", "content")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class KnowledgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand_id: UUID
    title: str
    category: KnowledgeCategory
    content: str
    active: bool
    created_at: datetime
    updated_at: datetime
