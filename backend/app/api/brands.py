from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Brand
from app.schemas.brand import BrandRead
from app.schemas.knowledge import KnowledgeRead, KnowledgeWrite
from app.services.knowledge import create_entry, list_entries

router = APIRouter(prefix="/api", tags=["brands"])


@router.get("/brands", response_model=list[BrandRead])
async def get_brands(session: AsyncSession = Depends(get_db)) -> list[Brand]:
    brands = await session.scalars(select(Brand).order_by(Brand.name))
    return list(brands)


@router.get("/brands/{brand_id}/knowledge", response_model=list[KnowledgeRead])
async def get_brand_knowledge(
    brand_id: UUID, session: AsyncSession = Depends(get_db)
) -> list:
    return await list_entries(session, brand_id)


@router.post(
    "/brands/{brand_id}/knowledge",
    response_model=KnowledgeRead,
    status_code=201,
)
async def post_brand_knowledge(
    brand_id: UUID,
    payload: KnowledgeWrite,
    session: AsyncSession = Depends(get_db),
) -> object:
    return await create_entry(session, brand_id, payload)
