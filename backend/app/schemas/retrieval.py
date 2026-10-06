from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import KnowledgeCategory


class RetrievalRequest(BaseModel):
    """Customer text to search. A supplied brand_id is accepted and ignored."""

    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1)
    brand_id: UUID | None = Field(
        default=None,
        description="Ignored. The conversation record determines the brand.",
    )

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class RetrievedKnowledge(BaseModel):
    knowledge_entry_id: UUID
    title: str
    category: KnowledgeCategory
    content: str
    score: float = Field(description="PostgreSQL full-text relevance score")
