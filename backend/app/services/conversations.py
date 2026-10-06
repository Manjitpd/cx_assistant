from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Brand, Conversation, Message
from app.models.enums import MessageAuthor
from app.schemas.conversation import MessageCreate


async def _require_brand(session: AsyncSession, brand_id: UUID) -> Brand:
    brand = await session.get(Brand, brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand


def _detail_options():
    return (
        joinedload(Conversation.brand),
        joinedload(Conversation.customer),
        joinedload(Conversation.order),
        selectinload(Conversation.messages),
    )


def _summary_options():
    return (
        joinedload(Conversation.brand),
        joinedload(Conversation.customer),
        joinedload(Conversation.order),
    )


async def list_conversations(session: AsyncSession, brand_id: UUID) -> list[Conversation]:
    await _require_brand(session, brand_id)
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.brand_id == brand_id)
        .options(*_summary_options())
        .order_by(Conversation.updated_at.desc())
    )
    return list(rows.unique())


async def get_conversation(
    session: AsyncSession, conversation_id: UUID, brand_id: UUID
) -> Conversation:
    await _require_brand(session, brand_id)
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.brand_id == brand_id)
        .options(*_detail_options())
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def _message_for_key(
    session: AsyncSession, conversation_id: UUID, idempotency_key: str
) -> Message | None:
    return await session.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.idempotency_key == idempotency_key,
        )
    )


async def add_message(
    session: AsyncSession,
    conversation_id: UUID,
    brand_id: UUID,
    payload: MessageCreate,
    author_type: MessageAuthor,
    idempotency_key: str | None = None,
) -> Conversation:
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Message must not be blank")
    conversation = await get_conversation(session, conversation_id, brand_id)
    if idempotency_key is not None:
        existing = await _message_for_key(session, conversation.id, idempotency_key)
        if existing is not None:
            return conversation
    session.add(
        Message(
            brand_id=conversation.brand_id,
            conversation_id=conversation.id,
            author_type=author_type,
            body=body,
            idempotency_key=idempotency_key,
        )
    )
    conversation.updated_at = datetime.now(timezone.utc)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if idempotency_key is not None:
            existing = await _message_for_key(session, conversation_id, idempotency_key)
            if existing is not None:
                return await get_conversation(session, conversation_id, brand_id)
        raise
    session.expire_all()
    return await get_conversation(session, conversation_id, brand_id)
