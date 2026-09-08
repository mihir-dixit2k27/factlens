"""FactLens FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.documents import router as documents_router
from app.api.routes.facts import router as facts_router
from app.api.routes.misc import (
    cases_router,
    health_router,
    metrics_router,
    query_router,
)
from app.api.routes.relationships import router as relationships_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import init_db

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize DB on startup."""
    logger.info("factlens_startup", version="1.0.0", llm_provider=settings.llm_provider)
    await init_db()
    # Ensure data dirs exist
    settings.incoming_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    yield
    logger.info("factlens_shutdown")


app = FastAPI(
    title="FactLens",
    description=(
        "Evidence-First Cross-Document Fact Reconciliation Engine. "
        "Extracts, grounds, normalizes, and reconciles facts across multiple PDFs."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS for local dev (frontend at :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(documents_router)
app.include_router(facts_router)
app.include_router(relationships_router)
app.include_router(query_router)
app.include_router(metrics_router)
app.include_router(health_router)
app.include_router(cases_router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "FactLens",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
