import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.schemas.errors import ErrorResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(OperationalError, database_unavailable_handler)
    app.add_exception_handler(InterfaceError, database_unavailable_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=detail).as_body(),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            detail="Request validation failed",
            errors=jsonable_encoder(exc.errors()),
        ).as_body(),
    )


async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Database unavailable for %s", request.url.path)
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(detail="Database unavailable").as_body(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail="Internal server error").as_body(),
    )
