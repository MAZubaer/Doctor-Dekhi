"""A patient finds a doctor and books a serial."""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.core.time import today_bd
from app.models import Notification, NotificationType, Patient
from tests.factories import WAITING, assert_error, serial_nos_notified

TOMORROW_SESSION = (dt.time(9, 0), dt.time(13, 0))


def booking(schedule_id: int, phone: str = "01712345678", name: str = "Md. Rahim Uddin") -> dict:
    return {"schedule_id": schedule_id, "patient_name": name, "phone": phone}


def tomorrow() -> dt.date:
    return today_bd() + dt.timedelta(days=1)


def test_booking_gives_the_first_serial_and_a_confirmation_sms(client, factory, db):
    schedule = factory.schedule(date=tomorrow(), session=TOMORROW_SESSION)

    response = client.post("/serials", json=booking(schedule.id))

    assert response.status_code == 201, response.text
    serial = response.json()
    assert serial["serial_no"] == 1
    assert serial["status"] == "waiting"
    assert serial["source"] == "app"
    assert serial["patient_name"] == "Md. Rahim Uddin"
    assert serial["phone"] == "017****5678"
    assert serial_nos_notified(db, schedule, NotificationType.CONFIRMATION) == [1]


def test_every_phone_format_is_stored_as_one_patient(client, factory, db):
    formats = ["+8801712345678", "8801712345678", "017-1234 5678"]
    schedules = [factory.schedule() for _ in formats]

    responses = [
        client.post("/serials", json=booking(schedule.id, phone, name=f"Name {letter}"))
        for schedule, phone, letter in zip(schedules, formats, "ABC")
    ]

    assert [response.status_code for response in responses] == [201, 201, 201]
    assert db.scalars(select(Patient.phone)).all() == ["01712345678"]
    assert {response.json()["patient_name"] for response in responses} == {"Name A"}


def test_invalid_phone_returns_422_naming_the_field(client, factory):
    schedule = factory.schedule()

    response = client.post("/serials", json=booking(schedule.id, phone="01212345678"))

    body = assert_error(response, 422, "VALIDATION_ERROR")
    assert [error["field"] for error in body["details"]] == ["phone"]
    assert "Bangladeshi mobile number" in body["details"][0]["message"]


def test_booking_twice_returns_409_with_the_existing_serial(client, factory):
    schedule = factory.schedule()
    first = client.post("/serials", json=booking(schedule.id)).json()

    response = client.post("/serials", json=booking(schedule.id, "+8801712345678"))

    body = assert_error(response, 409, "ALREADY_BOOKED")
    assert body["details"] == {"serial_id": first["id"], "serial_no": 1}


def test_full_schedule_returns_409(client, factory):
    schedule = factory.schedule(max_serials=2)
    factory.queue(schedule, WAITING, WAITING)

    response = client.post("/serials", json=booking(schedule.id))

    assert_error(response, 409, "SCHEDULE_FULL")


@pytest.mark.parametrize(
    "days_ago, session",
    [(1, (dt.time(9, 0), dt.time(13, 0))), (0, (dt.time(0, 0), dt.time(0, 0, 1)))],
    ids=["past date", "ended earlier today"],
)
def test_closed_schedule_returns_400(client, factory, days_ago, session):
    schedule = factory.schedule(date=today_bd() - dt.timedelta(days=days_ago), session=session)

    response = client.post("/serials", json=booking(schedule.id))

    assert_error(response, 400, "SCHEDULE_CLOSED")


@pytest.mark.parametrize(
    "unavailable",
    [{"is_available": False}, {"doctor_is_active": False}],
    ids=["schedule cancelled", "doctor inactive"],
)
def test_unavailable_doctor_returns_400(client, factory, unavailable):
    schedule = factory.schedule(**unavailable)

    response = client.post("/serials", json=booking(schedule.id))

    assert_error(response, 400, "DOCTOR_UNAVAILABLE")


def test_unknown_ids_return_404(client):
    assert_error(client.get("/hospitals/99/departments"), 404, "HOSPITAL_NOT_FOUND")
    assert_error(client.get("/doctors/available?department_id=99"), 404, "DEPARTMENT_NOT_FOUND")
    assert_error(client.post("/serials", json=booking(99)), 404, "SCHEDULE_NOT_FOUND")
    assert_error(client.get("/serials/99/status"), 404, "SERIAL_NOT_FOUND")


def test_available_doctors_shows_serials_left_and_rejects_past_dates(client, factory):
    schedule = factory.schedule(date=tomorrow(), session=TOMORROW_SESSION, max_serials=10)
    factory.queue(schedule, WAITING, WAITING, WAITING)
    department_id = schedule.doctor.department_id

    response = client.get(f"/doctors/available?department_id={department_id}&date={tomorrow()}")

    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["schedule_id"] == schedule.id
    assert (row["serials_booked"], row["serials_left"]) == (3, 7)

    yesterday = today_bd() - dt.timedelta(days=1)
    past = client.get(f"/doctors/available?department_id={department_id}&date={yesterday}")
    assert_error(past, 400, "DATE_IN_PAST")


def test_parallel_bookings_get_unique_serial_numbers(client, factory, db):
    patients = 8
    schedule = factory.schedule()
    phones = [factory.phone() for _ in range(patients)]
    start_together = Barrier(patients)

    def book(phone: str):
        start_together.wait()
        return client.post("/serials", json=booking(schedule.id, phone))

    with ThreadPoolExecutor(max_workers=patients) as pool:
        responses = list(pool.map(book, phones))

    assert [response.status_code for response in responses] == [201] * patients
    serial_numbers = sorted(response.json()["serial_no"] for response in responses)
    assert serial_numbers == list(range(1, patients + 1))
    db.rollback()
    assert db.scalar(select(func.count(Notification.id))) == patients
