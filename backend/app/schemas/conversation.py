from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ConversationStatus, MessageAuthor, OrderStatus


class BrandSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str


class CustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_number: str
    product_name: str
    status: OrderStatus
    total_cents: int
    currency: str
    placed_at: datetime
    delivered_at: datetime | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_type: MessageAuthor
    body: str
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject: str
    status: ConversationStatus
    updated_at: datetime
    brand: BrandSummary
    customer: CustomerSummary
    order: OrderSummary


class ConversationDetail(ConversationSummary):
    created_at: datetime
    messages: list[MessageRead]


class MessageCreate(BaseModel):
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned
