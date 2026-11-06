"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api_docs import API_DESCRIPTION, OPENAPI_TAGS
from app.config import settings
from app.core.errors import AppError, register_error_handlers
from app.database import DbSession
from app.routers import auth, doctors, hospitals, serials, staff
from app.schemas.common import (
    INTERNAL_ERROR_RESPONSE,
    ApiInfo,
    ApiLinks,
    HealthOut,
    error_response,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Database target: %s", settings.database_target)
    yield


app = FastAPI(
    title="Doctor Dekhi API",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
    responses={500: INTERNAL_ERROR_RESPONSE},
)

register_error_handlers(app)

# The order here is the order of the routes in the docs: the patient journey first.
app.include_router(hospitals.router)
app.include_router(doctors.router)
app.include_router(serials.router)
app.include_router(auth.router)
app.include_router(staff.router)


@app.get(
    "/",
    tags=["System"],
    summary="API information",
    description="Returns the API's name, version and useful links.",
)
def get_api_info() -> ApiInfo:
    return ApiInfo(
        name=app.title,
        version=app.version,
        links=ApiLinks(docs="/docs", scalar="/scalar", health="/health"),
    )


@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    description="Reports that the API is running and can reach the database.",
    responses={
        503: error_response(
            "The database cannot be reached",
            ("DATABASE_UNAVAILABLE", "Database is unavailable."),
        ),
    },
)
def health_check(db: DbSession) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Health check could not reach the database")
        raise AppError(503, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
    return HealthOut(status="ok")


@app.get("/scalar", include_in_schema=False)
def scalar_docs() -> HTMLResponse:
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
        telemetry=False,
    )
