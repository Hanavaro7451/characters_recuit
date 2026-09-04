from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


async def app_error_handler(
    _: Request,
    error: Exception,
) -> JSONResponse:
    if not isinstance(error, AppError):
        raise error

    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail},
    )

def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_exception_handler(
        AppError,
        app_error_handler,
    )
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
