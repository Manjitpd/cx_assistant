from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Brand, KnowledgeBaseEntry
from app.schemas.knowledge import KnowledgeWrite


def ensure_same_brand(given: UUID | None, expected: UUID) -> None:
    if given is not None and given != expected:
        raise HTTPException(status_code=422, detail="brand_id does not match this brand")


async def require_brand(session: AsyncSession, brand_id: UUID) -> Brand:
    brand = await session.get(Brand, brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand


async def require_entry(
    session: AsyncSession, knowledge_id: UUID, brand_id: UUID
) -> KnowledgeBaseEntry:
    entry = await session.scalar(
        select(KnowledgeBaseEntry).where(
            KnowledgeBaseEntry.id == knowledge_id,
            KnowledgeBaseEntry.brand_id == brand_id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return entry


async def list_entries(session: AsyncSession, brand_id: UUID) -> list[KnowledgeBaseEntry]:
    await require_brand(session, brand_id)
    rows = await session.scalars(
        select(KnowledgeBaseEntry)
        .where(KnowledgeBaseEntry.brand_id == brand_id)
        .order_by(KnowledgeBaseEntry.category, KnowledgeBaseEntry.title)
    )
    return list(rows)


async def create_entry(
    session: AsyncSession, brand_id: UUID, payload: KnowledgeWrite
) -> KnowledgeBaseEntry:
    await require_brand(session, brand_id)
    ensure_same_brand(payload.brand_id, brand_id)
    entry = KnowledgeBaseEntry(
        brand_id=brand_id,
        title=payload.title,
        category=payload.category,
        content=payload.content,
        active=payload.active,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def update_entry(
    session: AsyncSession,
    knowledge_id: UUID,
    brand_id: UUID,
    payload: KnowledgeWrite,
) -> KnowledgeBaseEntry:
    ensure_same_brand(payload.brand_id, brand_id)
    entry = await require_entry(session, knowledge_id, brand_id)
    entry.title = payload.title
    entry.category = payload.category
    entry.content = payload.content
    entry.active = payload.active
    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_entry(session: AsyncSession, knowledge_id: UUID, brand_id: UUID) -> None:
    entry = await require_entry(session, knowledge_id, brand_id)
    await session.delete(entry)
    await session.commit()
