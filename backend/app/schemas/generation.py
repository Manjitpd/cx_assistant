from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.retrieval import RetrievedKnowledge


class EvidenceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class GenerationStatus(str, Enum):
    AI_GENERATED = "AI_GENERATED"
    EDITED = "EDITED"
    APPROVED = "APPROVED"
    SENT = "SENT"


class GeneratedReply(BaseModel):
    suggested_reply: str
    evidence_status: EvidenceStatus
    warning: str | None = None
    used_knowledge_ids: list[UUID] = Field(default_factory=list)

    @field_validator("evidence_status", mode="before")
    @classmethod
    def normalize_evidence_status(cls, value: object) -> object:
        if value == "supported":
            return EvidenceStatus.SUPPORTED
        if value == "needs_review":
            return EvidenceStatus.HUMAN_REVIEW_REQUIRED
        return value


class GenerationState(BaseModel):
    id: UUID
    status: GenerationStatus
    suggested_reply: str
    edited_reply: str | None = None
    final_reply: str | None = None
    evidence_status: EvidenceStatus
    warning: str | None = None


class GenerationEdit(BaseModel):
    """Saves the agent's wording. A supplied brand_id is ignored."""

    model_config = ConfigDict(extra="ignore")

    edited_reply: str = Field(min_length=1)
    brand_id: UUID | None = None

    @field_validator("edited_reply")
    @classmethod
    def strip_reply(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class GenerateReplyRequest(BaseModel):
    """Client hints are accepted and ignored. The conversation owns the brand."""

    model_config = ConfigDict(extra="ignore")

    brand_id: UUID | None = None


class RetrievedContextItem(BaseModel):
    knowledge_entry_id: UUID
    title: str
    category: str
    content: str
    score: float


class GenerationLogRead(BaseModel):
    """Audit row for one draft. It never includes provider credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    customer_message_id: UUID
    brand_id: UUID
    retrieved_knowledge_ids: list[str]
    retrieved_context: list[RetrievedContextItem]
    model_name: str | None = None
    suggested_reply: str
    edited_reply: str | None = None
    final_reply: str | None = None
    evidence_status: EvidenceStatus
    warning: str | None = None
    error_detail: str | None = None
    created_at: datetime
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    status: GenerationStatus


class GenerateReplyResponse(BaseModel):
    suggested_reply: str
    retrieved_knowledge: list[RetrievedKnowledge]
    evidence_status: EvidenceStatus
    warning: str | None = None
    generation_id: UUID
    status: GenerationStatus
