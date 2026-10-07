"""
FastAPI application entry point.

Features:
- RESTful API for Smartlead data and report generation
- APScheduler for weekly automated reports
- Structured logging with secret redaction
- Async PostgreSQL via SQLAlchemy
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analytics, campaigns, clients, mailboxes, reports
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.models.database import create_all_tables
from app.scheduler import create_scheduler

# Bootstrap logging FIRST before any other module logs
settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # ---- Startup ----
    logger.info("=== Smartlead Weekly Mailbox Analytics starting ===")
    logger.info("Settings: %s", settings.safe_repr())

    # Create DB tables
    try:
        await create_all_tables()
        logger.info("Database tables verified/created")
    except Exception as exc:
        logger.warning(
            "Database initialization failed (PostgreSQL may not be running): %s. "
            "The application will start but database persistence is disabled.",
            exc,
        )

    # Start scheduler
    scheduler = create_scheduler(settings)
    if scheduler:
        scheduler.start()
        logger.info(
            "Scheduler started: reports every %s at %02d:%02d",
            settings.report_day,
            settings.report_hour,
            settings.report_minute,
        )
        app.state.scheduler = scheduler

    yield

    # ---- Shutdown ----
    logger.info("=== Smartlead Weekly Mailbox Analytics shutting down ===")
    if hasattr(app.state, "scheduler") and app.state.scheduler.running:
        app.state.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


app = FastAPI(
    title="Smartlead Weekly Mailbox Analytics",
    description=(
        "Production-ready API for generating weekly mailbox-level "
        "email delivery reports from Smartlead."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Register routers ----
app.include_router(reports.router)
app.include_router(clients.router)
app.include_router(campaigns.router)
app.include_router(mailboxes.router)
app.include_router(analytics.router)


from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/", include_in_schema=False)
async def serve_ui():
    index_file = frontend_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "name": "Smartlead Weekly Mailbox Analytics",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }



@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Health check endpoint. Does NOT expose any secrets."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "dry_run": settings.dry_run,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
