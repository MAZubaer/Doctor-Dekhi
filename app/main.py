"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.core.errors import AppError, register_error_handlers
from app.database import DbSession
from app.routers import doctors, hospitals, serials
from app.schemas.common import error_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Database target: %s", settings.database_target)
    yield


app = FastAPI(
    title="Doctor Dekhi API",
    description="Hospital serial and queue system for public hospitals in Bangladesh.",
    version="0.1.0",
    lifespan=lifespan,
)

register_error_handlers(app)

app.include_router(hospitals.router)
app.include_router(doctors.router)
app.include_router(serials.router)


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
    description="Reports that the API is running and can reach the database.",
    responses={
        503: error_response(
            "The database cannot be reached",
            ("DATABASE_UNAVAILABLE", "Database is unavailable."),
        ),
    },
)
def health_check(db: DbSession) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Health check could not reach the database")
        raise AppError(503, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
    return {"status": "ok"}
