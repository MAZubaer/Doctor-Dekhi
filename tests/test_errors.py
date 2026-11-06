"""Every failure comes back in the same JSON shape, and leaks nothing internal."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app
from app.services import hospital_service
from tests.factories import assert_error


def test_unknown_url_and_wrong_method_use_the_error_shape(client):
    assert_error(client.get("/no-such-page"), 404, "NOT_FOUND")
    assert_error(client.delete("/hospitals"), 405, "METHOD_NOT_ALLOWED")


@pytest.mark.parametrize(
    "request_args, fields",
    [
        (
            {
                "method": "POST",
                "url": "/serials",
                "content": "{not json",
                "headers": {"Content-Type": "application/json"},
            },
            {"body"},
        ),
        (
            {"method": "POST", "url": "/serials", "json": {}},
            {"schedule_id", "patient_name", "phone"},
        ),
        (
            {"method": "GET", "url": "/serials/2147483648/status"},
            {"serial_id"},
        ),
    ],
    ids=["malformed JSON", "missing fields", "ID too large for the database"],
)
def test_bad_input_returns_422_naming_each_field(client, request_args, fields):
    body = assert_error(client.request(**request_args), 422, "VALIDATION_ERROR")

    assert {error["field"] for error in body["details"]} == fields


def test_unexpected_error_returns_500_without_internal_details(monkeypatch):
    def fail(db):
        raise RuntimeError("password=hunter2 at db-host")

    monkeypatch.setattr(hospital_service, "list_hospitals", fail)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/hospitals")

    body = assert_error(response, 500, "INTERNAL_ERROR")
    assert "hunter2" not in response.text
    assert body["details"] is None


def test_health_reports_a_lost_database_as_503():
    class BrokenSession:
        def execute(self, statement):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_db] = BrokenSession
    try:
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert_error(response, 503, "DATABASE_UNAVAILABLE")
    assert "connection refused" not in response.text
