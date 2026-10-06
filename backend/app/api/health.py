from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_db)) -> HealthResponse:
    await session.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok")
