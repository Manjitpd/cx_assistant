from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIGenerationLog, Conversation, Message
from app.models.enums import MessageAuthor
from app.schemas.generation import GenerationState, GenerationStatus


def _state(log: AIGenerationLog) -> GenerationState:
    return GenerationState(
        id=log.id,
        status=GenerationStatus(log.status),
        suggested_reply=log.suggested_reply,
        edited_reply=log.edited_reply,
        final_reply=log.final_reply,
        evidence_status=log.evidence_status,
        warning=log.warning,
    )


def _working_text(log: AIGenerationLog) -> str:
    if log.edited_reply:
        return log.edited_reply
    return log.suggested_reply


async def _lock_generation(session: AsyncSession, generation_id: UUID) -> AIGenerationLog:
    log = await session.scalar(
        select(AIGenerationLog).where(AIGenerationLog.id == generation_id).with_for_update()
    )
    if log is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return log


async def edit_generation(
    session: AsyncSession,
    generation_id: UUID,
    edited_reply: str,
    *,
    brand_id: UUID | None = None,
) -> GenerationState:
    del brand_id
    text = edited_reply.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Edited reply must not be blank")
    log = await _lock_generation(session, generation_id)
    if log.status == GenerationStatus.SENT.value:
        raise HTTPException(status_code=409, detail="Sent generations cannot be edited")
    original = log.suggested_reply
    if text == original:
        log.edited_reply = None
        log.status = GenerationStatus.AI_GENERATED.value
    elif text == _working_text(log):
        pass
    else:
        log.edited_reply = text
        log.status = GenerationStatus.EDITED.value
    log.suggested_reply = original
    await session.commit()
    await session.refresh(log)
    return _state(log)


async def approve_generation(
    session: AsyncSession,
    generation_id: UUID,
    *,
    brand_id: UUID | None = None,
) -> GenerationState:
    del brand_id
    log = await _lock_generation(session, generation_id)
    if log.status == GenerationStatus.SENT.value:
        raise HTTPException(status_code=409, detail="Sent generations cannot be approved")
    if log.status != GenerationStatus.APPROVED.value:
        log.status = GenerationStatus.APPROVED.value
        await session.commit()
        await session.refresh(log)
    return _state(log)


async def send_generation(
    session: AsyncSession,
    generation_id: UUID,
    *,
    brand_id: UUID | None = None,
) -> Message:
    del brand_id
    log = await _lock_generation(session, generation_id)
    if log.status == GenerationStatus.SENT.value:
        message = await session.get(Message, log.sent_message_id)
        if message is None:
            raise HTTPException(status_code=404, detail="Sent message not found")
        return message
    if log.status != GenerationStatus.APPROVED.value:
        raise HTTPException(
            status_code=409,
            detail="Generation must be approved before it can be sent",
        )
    conversation = await session.get(Conversation, log.conversation_id)
    if conversation is None or conversation.brand_id != log.brand_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    final_reply = _working_text(log)
    message = Message(
        brand_id=conversation.brand_id,
        conversation_id=conversation.id,
        author_type=MessageAuthor.AGENT,
        body=final_reply,
    )
    conversation.updated_at = datetime.now(timezone.utc)
    session.add(message)
    await session.flush()
    log.final_reply = final_reply
    log.sent_message_id = message.id
    log.sent_author_type = MessageAuthor.AGENT.value
    log.status = GenerationStatus.SENT.value
    await session.commit()
    await session.refresh(message)
    return message
