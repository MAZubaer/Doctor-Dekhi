"""Staff login."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.phone import normalize_phone
from app.core.security import create_access_token, spend_verify_time, verify_password
from app.models import User
from app.schemas.auth import LoginResponse, UserSummary


def login(db: Session, phone: str, password: str) -> LoginResponse:
    """Check credentials and issue an access token.

    An unknown phone and a wrong password give the same error. The disabled check
    runs after the password check, so only the real owner can learn that status.
    """
    user = _find_user(db, phone)
    if user is None:
        spend_verify_time()
        raise _invalid_credentials()
    if not verify_password(password, user.hashed_password):
        raise _invalid_credentials()
    if not user.is_active:
        raise ForbiddenError("ACCOUNT_DISABLED", "This account has been disabled.")

    return LoginResponse(
        access_token=create_access_token(user),
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserSummary.from_user(user),
    )


def _find_user(db: Session, phone: str) -> User | None:
    try:
        normalized_phone = normalize_phone(phone)
    except ValueError:
        return None
    return db.scalar(
        select(User).options(joinedload(User.hospital)).where(User.phone == normalized_phone)
    )


def _invalid_credentials() -> UnauthorizedError:
    return UnauthorizedError("INVALID_CREDENTIALS", "Incorrect phone number or password.")
