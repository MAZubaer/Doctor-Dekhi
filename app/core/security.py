"""Password hashing and JWT access tokens."""

import datetime as dt

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.errors import UnauthorizedError
from app.core.time import now_bd
from app.models import User

JWT_ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(password, hashed_password)
    except ValueError:
        # passlib rejects NUL characters and oversized input. Neither can match.
        return False


def spend_verify_time() -> None:
    """Take as long as a real password check, so timing cannot reveal unknown phones."""
    pwd_context.dummy_verify()


def create_access_token(user: User) -> str:
    issued_at = now_bd()
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "hospital_id": user.hospital_id,
        "iat": issued_at,
        "exp": issued_at + dt.timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_user_id(token: str) -> int:
    """Return the user ID from a token, or raise a 401 if the token is not valid."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        return int(payload["sub"])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError(
            "TOKEN_EXPIRED",
            "The access token has expired. Please log in again.",
        ) from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise UnauthorizedError("INVALID_TOKEN", "The access token is invalid.") from exc
