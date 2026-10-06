from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.retrieval import RetrievalRequest, RetrievedKnowledge
from app.services.retrieval import retrieve_knowledge

router = APIRouter(prefix="/api", tags=["retrieval"])


@router.post(
    "/conversations/{conversation_id}/retrieve",
    response_model=list[RetrievedKnowledge],
)
async def post_retrieve(
    conversation_id: UUID,
    payload: RetrievalRequest,
    brand_id: UUID | None = Query(
        default=None,
        description="Ignored. The conversation record determines the brand.",
    ),
    session: AsyncSession = Depends(get_db),
) -> list[RetrievedKnowledge]:
    claimed_brand_id = payload.brand_id if payload.brand_id is not None else brand_id
    return await retrieve_knowledge(
        session,
        conversation_id=conversation_id,
        customer_message=payload.message,
        brand_id=claimed_brand_id,
    )
