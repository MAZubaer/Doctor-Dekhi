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
                    "message": "No serials left for this doctor today.",
                    "details": None,
                }
            ]
        }
    )

    error: str
    message: str
    details: Any | None = None


def error_response(description: str, *errors: tuple[str, str]) -> dict[str, Any]:
    """Build a `responses` entry that shows each (code, message) in Swagger."""
    examples = {
        code: {"summary": code, "value": {"error": code, "message": message, "details": None}}
        for code, message in errors
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

INTERNAL_ERROR_RESPONSE = error_response(
    "Unexpected server error",
    ("INTERNAL_ERROR", "Something went wrong on our side. Please try again."),
)
