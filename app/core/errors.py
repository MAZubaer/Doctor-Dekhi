"""Application errors and the global handlers that give them one JSON shape."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)

HTTP_ERROR_CODES = {
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
}


class AppError(Exception):
    """An expected failure that is returned to the client as a JSON error."""

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    def __init__(self, error_code: str, message: str, details: Any | None = None) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, error_code, message, details)


class BadRequestError(AppError):
    def __init__(self, error_code: str, message: str, details: Any | None = None) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, error_code, message, details)


class ConflictError(AppError):
    def __init__(self, error_code: str, message: str, details: Any | None = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, error_code, message, details)


class UnauthorizedError(AppError):
    def __init__(self, error_code: str, message: str, details: Any | None = None) -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            error_code,
            message,
            details,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenError(AppError):
    def __init__(self, error_code: str, message: str, details: Any | None = None) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, error_code, message, details)


def error_json(
    status_code: int,
    error: str,
    message: str,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=error, message=message, details=details)
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def field_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    """Turn Pydantic errors into a readable [{field, message}] list."""
    errors = []
    for error in exc.errors():
        location = [str(part) for part in error["loc"]]
        # The first part only says where the value came from: body, query or path.
        field = ".".join(location[1:]) or location[0]
        if error["type"] == "json_invalid":
            field = "body"
        message = error["msg"].removeprefix("Value error, ")
        errors.append({"field": field, "message": message})
    return errors


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return error_json(exc.status_code, exc.error_code, exc.message, exc.details, exc.headers)


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_json(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "VALIDATION_ERROR",
        "Some fields are missing or invalid.",
        field_errors(exc),
    )


async def handle_http_error(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Cover framework errors, such as an unknown URL or the wrong HTTP method."""
    error = HTTP_ERROR_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    return error_json(exc.status_code, error, str(exc.detail), headers=exc.headers)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled error on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return error_json(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "Something went wrong on our side. Please try again.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
