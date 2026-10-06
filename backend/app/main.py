import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.brands import router as brands_router
from app.api.conversations import router as conversations_router
from app.api.generation import router as generation_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.retrieval import router as retrieval_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.errors import register_exception_handlers

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(brands_router)
    app.include_router(knowledge_router)
    app.include_router(conversations_router)
    app.include_router(retrieval_router)
    app.include_router(generation_router)
    return app


app = create_app()
