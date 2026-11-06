"""Shared fixtures. The tests wipe the Neon dev branch, so they refuse to run on main."""

import os

from pydantic import ValidationError
from sqlalchemy.engine import make_url

# Must run before anything imports the app. A shell with APP_ENV=prod stays prod here
# and is refused below, so only an unset APP_ENV is defaulted to dev.
os.environ.setdefault("APP_ENV", "dev")

try:
    from app.config import settings
except ValidationError as exc:
    reasons = "; ".join(error["msg"] for error in exc.errors())
    raise SystemExit(f"Refusing to run tests: {reasons}") from None


def is_same_database(first_url: str, second_url: str) -> bool:
    """Compare two URLs by server and database, so different spellings still match."""
    first, second = make_url(first_url), make_url(second_url)
    first_host = (first.host or "").replace("-pooler", "")
    second_host = (second.host or "").replace("-pooler", "")
    return first_host == second_host and first.database == second.database


if settings.app_env != "dev":
    raise SystemExit("Refusing to run tests: the target is main. They only run with APP_ENV=dev.")
if is_same_database(settings.dev_database_url, settings.database_url):
    raise SystemExit("Refusing to run tests: DEV_DATABASE_URL points at the main database.")

# These imports build the engine, so they stay below the checks above.
from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import seed  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Hospital, User, UserRole  # noqa: E402
from tests.factories import PASSWORD, Factory  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def fresh_schema() -> Iterator[None]:
    """Build an empty schema for this run, then restore the demo data for dev."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    seed.reset_tables()
    with SessionLocal.begin() as db:
        seed.seed(db)


@pytest.fixture(autouse=True)
def empty_tables(fresh_schema: None) -> None:
    """Start every test from empty tables, so tests cannot affect each other."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def factory(db: Session) -> Factory:
    return Factory(db)


@pytest.fixture
def login(client: TestClient) -> Callable[[User], dict[str, str]]:
    """Log a user in through the API and return their auth headers."""

    def log_in(user: User) -> dict[str, str]:
        response = client.post(
            "/auth/login",
            data={"username": user.phone, "password": PASSWORD},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return log_in


@pytest.fixture
def login_as(
    factory: Factory,
    login: Callable[[User], dict[str, str]],
) -> Callable[[UserRole, Hospital | None], dict[str, str]]:
    """Create a user with this role and return their auth headers."""

    def log_in_new_user(role: UserRole, hospital: Hospital | None = None) -> dict[str, str]:
        return login(factory.user(role, hospital))

    return log_in_new_user
