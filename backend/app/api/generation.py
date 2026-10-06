from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import AIGenerationLog, Message
from app.schemas.conversation import MessageRead
from app.schemas.generation import (
    GenerateReplyRequest,
    GenerateReplyResponse,
    GenerationEdit,
    GenerationLogRead,
    GenerationState,
)
from app.services.ai_provider import AIProvider, get_ai_provider
from app.services.approval import approve_generation, edit_generation, send_generation
from app.services.generation import generate_conversation_reply, list_generation_logs

router = APIRouter(prefix="/api", tags=["generation"])


def get_reply_provider() -> AIProvider:
    return get_ai_provider()


@router.get(
    "/conversations/{conversation_id}/generations",
    response_model=list[GenerationLogRead],
)
async def get_generation_history(
    conversation_id: UUID,
    brand_id: UUID = Query(description="Brand that must own this conversation"),
    session: AsyncSession = Depends(get_db),
) -> list[AIGenerationLog]:
    return await list_generation_logs(session, conversation_id, brand_id)


@router.post(
    "/conversations/{conversation_id}/generate-reply",
    response_model=GenerateReplyResponse,
)
async def post_generate_reply(
    conversation_id: UUID,
    payload: Annotated[GenerateReplyRequest | None, Body()] = None,
    brand_id: UUID | None = Query(
        default=None,
        description="Ignored. The conversation record determines the brand.",
    ),
    session: AsyncSession = Depends(get_db),
    provider: AIProvider = Depends(get_reply_provider),
) -> GenerateReplyResponse:
    claimed_brand_id = payload.brand_id if payload is not None and payload.brand_id is not None else brand_id
    return await generate_conversation_reply(
        session,
        conversation_id,
        provider=provider,
        brand_id=claimed_brand_id,
    )


@router.put("/ai-generations/{generation_id}", response_model=GenerationState)
async def put_generation(
    generation_id: UUID,
    payload: GenerationEdit,
    brand_id: UUID | None = Query(
        default=None,
        description="Ignored. The generation record determines the brand.",
    ),
    session: AsyncSession = Depends(get_db),
) -> GenerationState:
    claimed_brand_id = payload.brand_id if payload.brand_id is not None else brand_id
    return await edit_generation(
        session,
        generation_id,
        payload.edited_reply,
        brand_id=claimed_brand_id,
    )


@router.post("/ai-generations/{generation_id}/approve", response_model=GenerationState)
async def post_approve_generation(
    generation_id: UUID,
    brand_id: UUID | None = Query(
        default=None,
        description="Ignored. The generation record determines the brand.",
    ),
    session: AsyncSession = Depends(get_db),
) -> GenerationState:
    return await approve_generation(session, generation_id, brand_id=brand_id)


@router.post("/ai-generations/{generation_id}/send", response_model=MessageRead)
async def post_send_generation(
    generation_id: UUID,
    brand_id: UUID | None = Query(
        default=None,
        description="Ignored. The generation record determines the brand.",
    ),
    session: AsyncSession = Depends(get_db),
) -> Message:
    return await send_generation(session, generation_id, brand_id=brand_id)
