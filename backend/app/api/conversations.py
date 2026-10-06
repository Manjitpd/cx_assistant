from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.enums import MessageAuthor
from app.schemas.conversation import ConversationDetail, ConversationSummary, MessageCreate
from app.services.conversations import add_message, get_conversation, list_conversations

router = APIRouter(prefix="/api", tags=["conversations"])


def require_idempotency_key(idempotency_key: Annotated[str, Header()]) -> str:
    cleaned = idempotency_key.strip()
    if not cleaned or len(cleaned) > 80 or any(character.isspace() for character in cleaned):
        raise HTTPException(
            status_code=422, detail="Idempotency-Key must be 1 to 80 characters"
        )
    return cleaned


@router.get("/conversations", response_model=list[ConversationSummary])
async def get_conversations(
    brand_id: UUID = Query(description="Brand whose inbox to list"),
    session: AsyncSession = Depends(get_db),
) -> list:
    return await list_conversations(session, brand_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_detail(
    conversation_id: UUID,
    brand_id: UUID = Query(description="Brand that must own this conversation"),
    session: AsyncSession = Depends(get_db),
) -> object:
    return await get_conversation(session, conversation_id, brand_id)


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationDetail)
async def post_customer_message(
    conversation_id: UUID,
    payload: MessageCreate,
    brand_id: UUID = Query(description="Brand that must own this conversation"),
    session: AsyncSession = Depends(get_db),
) -> object:
    return await add_message(
        session, conversation_id, brand_id, payload, MessageAuthor.CUSTOMER
    )


@router.post(
    "/conversations/{conversation_id}/manual-reply",
    response_model=ConversationDetail,
)
async def post_manual_reply(
    conversation_id: UUID,
    payload: MessageCreate,
    brand_id: UUID = Query(description="Brand that must own this conversation"),
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_db),
) -> object:
    return await add_message(
        session,
        conversation_id,
        brand_id,
        payload,
        MessageAuthor.AGENT,
        idempotency_key,
    )
