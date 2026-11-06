"""The root route is an uptime ping target, so it must never need the database."""

import pytest
from sqlalchemy import event

from app.config import settings
from app.database import engine
from app.services import demo_service


@pytest.fixture
def database_activity():
    """Record every connection checkout and SQL statement made during a test."""
    activity = []

    def record(*args) -> None:
        activity.append(args)

    event.listen(engine, "checkout", record)
    event.listen(engine, "before_cursor_execute", record)
    yield activity
    event.remove(engine, "checkout", record)
    event.remove(engine, "before_cursor_execute", record)


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_root_answers_without_touching_the_database(
    client, database_activity, monkeypatch, method
):
    # With demo mode due to run, any database use on this route would show up here.
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(demo_service, "_last_run_date", None)

    response = client.request(method, "/")

    assert response.status_code == 200, response.text
    assert database_activity == []


def test_activity_check_detects_real_database_use(client, database_activity):
    assert client.get("/health").status_code == 200

    assert database_activity != []
