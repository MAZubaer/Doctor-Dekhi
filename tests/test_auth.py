"""Staff log in, and the API rejects every token it should not trust."""

import datetime as dt

import jwt
import pytest

from app.config import settings
from app.core.security import JWT_ALGORITHM
from app.models import UserRole
from tests.factories import PASSWORD, assert_error


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def token_payload(user_id: int, expires_in: dt.timedelta) -> dict:
    now = dt.datetime.now(dt.UTC)
    return {"sub": str(user_id), "iat": now - dt.timedelta(hours=2), "exp": now + expires_in}


@pytest.mark.parametrize(
    "role, sees_hospital",
    [
        (UserRole.SUPER_ADMIN, False),
        (UserRole.HOSPITAL_ADMIN, True),
        (UserRole.STAFF, True),
    ],
)
def test_each_role_can_log_in_and_read_their_profile(client, factory, role, sees_hospital):
    hospital = factory.hospital() if sees_hospital else None
    user = factory.user(role, hospital)

    login = client.post("/auth/login", data={"username": user.phone, "password": PASSWORD})

    assert login.status_code == 200, login.text
    assert login.json()["user"]["role"] == role
    assert login.json()["token_type"] == "bearer"

    me = client.get("/auth/me", headers=bearer(login.json()["access_token"]))
    assert me.status_code == 200, me.text
    assert me.json()["id"] == user.id
    assert me.json()["hospital_id"] == (hospital.id if hospital else None)


def test_wrong_password_and_unknown_phone_give_identical_errors(client, factory):
    user = factory.user(UserRole.STAFF, factory.hospital())

    wrong_password = client.post(
        "/auth/login", data={"username": user.phone, "password": "wrong-password"}
    )
    unknown_phone = client.post(
        "/auth/login", data={"username": "01999999999", "password": PASSWORD}
    )

    assert_error(wrong_password, 401, "INVALID_CREDENTIALS")
    assert wrong_password.status_code == unknown_phone.status_code
    assert wrong_password.json() == unknown_phone.json()


def test_no_token_returns_401(client):
    response = client.get("/auth/me")

    assert_error(response, 401, "NOT_AUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_tampered_tokens_return_401(client, factory):
    user = factory.user(UserRole.STAFF, factory.hospital())
    payload = token_payload(user.id, dt.timedelta(hours=1))
    real_token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    header, _, signature = real_token.split(".")
    forged_body = jwt.encode(
        {**payload, "sub": "999"}, settings.jwt_secret, algorithm=JWT_ALGORITHM
    ).split(".")[1]
    tokens = {
        "edited payload": f"{header}.{forged_body}.{signature}",
        "signed with another key": jwt.encode(payload, "x" * 40, algorithm=JWT_ALGORITHM),
        "not a token": "not-a-token",
    }

    for token in tokens.values():
        assert_error(client.get("/auth/me", headers=bearer(token)), 401, "INVALID_TOKEN")


def test_expired_token_returns_401(client, factory):
    user = factory.user(UserRole.STAFF, factory.hospital())
    payload = token_payload(user.id, dt.timedelta(minutes=-1))
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)

    response = client.get("/auth/me", headers=bearer(token))

    assert_error(response, 401, "TOKEN_EXPIRED")


def test_deactivated_user_loses_access_at_once(client, factory, db, login):
    user = factory.user(UserRole.STAFF, factory.hospital())
    headers = login(user)
    assert client.get("/auth/me", headers=headers).status_code == 200

    user.is_active = False
    db.commit()

    assert_error(client.get("/auth/me", headers=headers), 401, "INVALID_TOKEN")

    # Only the real owner, with the right password, learns the account is disabled.
    wrong = client.post("/auth/login", data={"username": user.phone, "password": "wrong"})
    right = client.post("/auth/login", data={"username": user.phone, "password": PASSWORD})
    assert_error(wrong, 401, "INVALID_CREDENTIALS")
    assert_error(right, 403, "ACCOUNT_DISABLED")
