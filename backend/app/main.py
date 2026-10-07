from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import Settings, get_settings
from app.middleware import ApiKeyMiddleware, RequestIdMiddleware
from app.repositories.sqlite import SqliteRepository
from app.routers import analytics, governance, health, jobs, reviews, themes
from app.schemas.common import ErrorBody
from app.services.analytics_service import AnalyticsService
from app.services.governance_service import GovernanceService
from app.services.ingestion_service import sweep_orphaned_uploads
from app.services.job_service import JobService
from app.services.ml_engine.worker import WorkerSupervisor
from app.services.theme_service import ThemeService
from app.utils.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    setup_logging(settings.log_level)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    repo = SqliteRepository(settings.sqlite_path)
    repo.init()
    worker = WorkerSupervisor(settings)
    job_service = JobService(repo, settings, worker)
    job_service.recover_on_startup()
    sweep_orphaned_uploads(settings.uploads_dir)
    worker.start()
    app.state.repo = repo
    app.state.worker = worker
    app.state.jobs = job_service
    app.state.analytics = AnalyticsService(repo, job_service, settings)
    app.state.themes = ThemeService(repo, job_service, settings)
    app.state.governance = GovernanceService(repo, job_service, settings)

    stop = asyncio.Event()

    async def retention_loop() -> None:
        while not stop.is_set():
            try:
                job_service.expire_old_jobs()
                sweep_orphaned_uploads(settings.uploads_dir)
                timed = job_service.fail_timed_out()
                if timed:
                    worker.restart()
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        worker.stop_all()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    application = FastAPI(
        title="Feedback & Review Analyzer API",
        version=__version__,
        description="REST API that queues review-file analysis jobs and serves dashboard analytics.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        responses={
            400: {"model": ErrorBody},
            401: {"model": ErrorBody},
            404: {"model": ErrorBody},
            409: {"model": ErrorBody},
            422: {"model": ErrorBody},
            500: {"model": ErrorBody},
        },
    )
    application.state.settings = settings

    origins = settings.cors_origins
    allow_credentials = "*" not in origins
    application.add_middleware(ApiKeyMiddleware)
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
        expose_headers=["Location", "Content-Disposition", "X-Request-ID"],
    )

    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    prefix = "/api/v1"
    application.include_router(health.router, prefix=prefix)
    application.include_router(reviews.router, prefix=prefix)
    application.include_router(jobs.router, prefix=prefix)
    application.include_router(analytics.router, prefix=prefix)
    application.include_router(themes.router, prefix=prefix)
    application.include_router(governance.router, prefix=prefix)
    return application


app = create_app()
