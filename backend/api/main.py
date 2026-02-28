"""FastAPI application for Voronode invoice processing."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.db import open_pool, close_pool, init_db
from voronode_logging import VoronodeLogger, CorrelationMiddleware, get_logger

VoronodeLogger.configure("voronode-api", level=settings.log_level)

logger = get_logger(__name__)

from backend.api.routes import router

# Create FastAPI app
app = FastAPI(
    title="Voronode Invoice Processing API",
    description="Autonomous Financial Risk & Compliance System - Invoice Intelligence",
    version="0.2.0",
)

# Correlation ID propagation + HTTP request logging
app.add_middleware(CorrelationMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("voronode_api_starting", version="0.2.0")
    open_pool()
    init_db()
    logger.info("db_pool_ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("voronode_api_shutting_down")
    close_pool()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Voronode Invoice Processing API",
        "version": "0.2.0",
        "status": "running",
    }
