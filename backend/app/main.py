"""FastAPI application entry point for the Monthly Budget API."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database import engine
from app.logging import configure_logging, get_logger
from app.routers import health

# Configure structured logging as early as possible so all startup
# log messages are captured in the correct format.
configure_logging()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    # --- Startup ---
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        environment=settings.environment,
    )

    yield

    # --- Shutdown ---
    logger.info("application_shutdown", app_name=settings.app_name)
    await engine.dispose()


app = FastAPI(
    title="Monthly Budget API",
    description="Backend API for the Monthly Budget application.",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS — allow the Vite dev server to send credentialed requests
cors_origins = ["http://localhost:5173"] if settings.is_development else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Prometheus metrics instrumentation.
# The /metrics endpoint is exposed automatically by the instrumentator.
Instrumentator().instrument(app).expose(app)

# Register routers
app.include_router(health.router)
