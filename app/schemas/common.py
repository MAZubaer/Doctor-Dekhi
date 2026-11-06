"""Schemas and OpenAPI helpers shared across the API."""

from typing import Any

from pydantic import BaseModel, ConfigDict

# Largest value of a PostgreSQL INTEGER. A bigger ID would fail in the database
# as a 500, so it is rejected as a validation error instead.
MAX_DB_ID = 2_147_483_647


class ErrorResponse(BaseModel):
    """The JSON shape of every error returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": "SCHEDULE_FULL",
                    "message": "No serials left for this doctor on this schedule.",
                    "details": None,
                }
            ]
        }
    )

    error: str
    message: str
    details: Any | None = None


class ApiLinks(BaseModel):
    docs: str
    scalar: str
    health: str


class ApiInfo(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Doctor Dekhi API",
                    "version": "0.1.0",
                    "links": {"docs": "/docs", "scalar": "/scalar", "health": "/health"},
                }
            ]
        }
    )

    name: str
    version: str
    links: ApiLinks


class HealthOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: str


def error_response(description: str, *errors: tuple[Any, ...]) -> dict[str, Any]:
    """Build a `responses` entry that shows each (code, message[, details]) in Swagger."""
    examples = {
        code: {
            "summary": code,
            "value": {
                "error": code,
                "message": message,
                "details": details[0] if details else None,
            },
        }
        for code, message, *details in errors
    }
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": {"examples": examples}},
    }


VALIDATION_RESPONSE: dict[str, Any] = {
    "model": ErrorResponse,
    "description": "The request has missing or invalid fields",
    "content": {
        "application/json": {
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "Some fields are missing or invalid.",
                "details": [
                    {
                        "field": "phone",
                        "message": (
                            "Enter a valid Bangladeshi mobile number, for example "
                            "01712345678 or +8801712345678."
                        ),
                    }
                ],
            }
        }
    },
}

UNAUTHORIZED_RESPONSE = error_response(
    "The token is missing, invalid or expired",
    ("NOT_AUTHENTICATED", "Log in to use this endpoint."),
    ("INVALID_TOKEN", "The access token is invalid."),
    ("TOKEN_EXPIRED", "The access token has expired. Please log in again."),
)

INTERNAL_ERROR_RESPONSE = error_response(
    "Unexpected server error",
    ("INTERNAL_ERROR", "Something went wrong on our side. Please try again."),
)
