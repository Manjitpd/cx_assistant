from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.knowledge import KnowledgeRead, KnowledgeWrite
from app.services.knowledge import delete_entry, require_entry, update_entry

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/knowledge/{knowledge_id}", response_model=KnowledgeRead)
async def get_knowledge(
    knowledge_id: UUID,
    brand_id: UUID = Query(description="Brand that must own this entry"),
    session: AsyncSession = Depends(get_db),
) -> object:
    return await require_entry(session, knowledge_id, brand_id)


@router.put("/knowledge/{knowledge_id}", response_model=KnowledgeRead)
async def put_knowledge(
    knowledge_id: UUID,
    payload: KnowledgeWrite,
    brand_id: UUID = Query(description="Brand that must own this entry"),
    session: AsyncSession = Depends(get_db),
) -> object:
    return await update_entry(session, knowledge_id, brand_id, payload)


@router.delete("/knowledge/{knowledge_id}", status_code=204)
async def delete_knowledge(
    knowledge_id: UUID,
    brand_id: UUID = Query(description="Brand that must own this entry"),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await delete_entry(session, knowledge_id, brand_id)
    return Response(status_code=204)
