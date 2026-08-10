import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status

from taxlens.api.routes.auth import admin_router
from taxlens.api.routes.auth import router as auth_router
from taxlens.api.routes.comparisons import router as comparisons_router
from taxlens.api.routes.documents import router as documents_router
from taxlens.api.routes.evaluation import router as evaluation_router
from taxlens.api.routes.internal_jobs import router as internal_jobs_router
from taxlens.api.routes.questions import router as questions_router
from taxlens.api.routes.search import router as search_router
from taxlens.config import get_settings
from taxlens.db import database_is_ready

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("Starting %s in %s", settings.app_name, settings.app_env)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(documents_router)
    app.include_router(evaluation_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(comparisons_router)
    app.include_router(questions_router)
    app.include_router(search_router)
    app.include_router(internal_jobs_router)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "taxlens_request_id": request_id,
                    "taxlens_method": request.method,
                    "taxlens_path": request.url.path,
                    "taxlens_duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "taxlens_request_id": request_id,
                "taxlens_method": request.method,
                "taxlens_path": request.url.path,
                "taxlens_status_code": response.status_code,
                "taxlens_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "taxlens-api"}

    @app.get("/ready", tags=["system"])
    def ready() -> dict[str, str]:
        if not database_is_ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "not_ready", "dependency": "database"},
            )
        return {"status": "ready"}

    return app


app = create_app()
