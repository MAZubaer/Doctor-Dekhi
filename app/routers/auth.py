"""Staff login and profile routes."""

from typing import Annotated

from fastapi import APIRouter, Form

from app.core.deps import CurrentUser
from app.database import DbSession
from app.schemas.auth import LoginResponse, UserProfile
from app.schemas.common import UNAUTHORIZED_RESPONSE, VALIDATION_RESPONSE, error_response
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    summary="Log in",
    description=(
        "Logs in a staff member and returns a bearer token.\n\n"
        "Send a form with the phone number as `username`, for example `01700000012`, "
        "and the `password`. In Swagger UI, use the **Authorize** button with a demo "
        "login from the top of this page."
    ),
    responses={
        401: error_response(
            "The phone number or password is wrong",
            ("INVALID_CREDENTIALS", "Incorrect phone number or password."),
        ),
        403: error_response(
            "The account is disabled",
            ("ACCOUNT_DISABLED", "This account has been disabled."),
        ),
        422: VALIDATION_RESPONSE,
    },
)
def login(
    username: Annotated[
        str,
        Form(description="The staff member's phone number.", examples=["01700000012"]),
    ],
    password: Annotated[
        str,
        Form(examples=["Demo@1234"], json_schema_extra={"format": "password"}),
    ],
    db: DbSession,
) -> LoginResponse:
    return auth_service.login(db, username, password)


@router.get(
    "/me",
    summary="Show the logged-in user",
    description="Returns the profile of the user who owns the bearer token.",
    responses={401: UNAUTHORIZED_RESPONSE},
)
def get_me(user: CurrentUser) -> UserProfile:
    return UserProfile.from_user(user)
