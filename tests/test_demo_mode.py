"""Demo mode keeps the deployed demo usable on any day, and only ever adds data."""

import datetime as dt

from sqlalchemy import func, select

from app.config import settings
from app.core.time import today_bd
from app.database import Base
from app.models import Doctor, DoctorSchedule, Serial
from app.services import demo_service
from app.services.demo_service import (
    DUTY_SESSION,
    DUTY_SPECIALTY,
    EVENING_SESSION,
    MORNING_SESSION,
    ensure_demo_data,
)
from tests.factories import WAITING


def row_counts(db) -> dict[str, int]:
    return {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }


def sessions_of(db, doctor_id: int) -> set[tuple[dt.date, dt.time]]:
    db.rollback()
    return set(
        db.execute(
            select(DoctorSchedule.date, DoctorSchedule.start_time).where(
                DoctorSchedule.doctor_id == doctor_id
            )
        ).tuples()
    )


def expected_sessions(first_day: dt.date, *sessions) -> set[tuple[dt.date, dt.time]]:
    return {
        (first_day + dt.timedelta(days=offset), start_time)
        for offset in range(7)
        for start_time, _ in sessions
    }


def duty_schedule_today(db, today: dt.date | None = None) -> DoctorSchedule:
    db.rollback()
    return db.scalar(
        select(DoctorSchedule)
        .join(DoctorSchedule.doctor)
        .where(Doctor.specialty == DUTY_SPECIALTY, DoctorSchedule.date == (today or today_bd()))
    )


def test_doctors_get_seven_days_of_sessions(factory, db):
    schedule = factory.schedule(session=MORNING_SESSION)

    ensure_demo_data(db)

    assert sessions_of(db, schedule.doctor_id) == expected_sessions(
        today_bd(), MORNING_SESSION, EVENING_SESSION
    )


def test_each_hospital_gets_a_duty_session_with_a_queue_in_progress(client, factory, db):
    factory.hospital()

    ensure_demo_data(db)

    duty = duty_schedule_today(db)
    assert sessions_of(db, duty.doctor_id) == expected_sessions(today_bd(), DUTY_SESSION)
    statuses = list(
        db.scalars(
            select(Serial.status).where(Serial.schedule_id == duty.id).order_by(Serial.serial_no)
        )
    )
    assert statuses == ["done", "done", "missed", "serving", *["waiting"] * 4]
    assert duty.current_serial == 4


def test_duty_session_can_be_booked_right_now(client, factory, db):
    factory.hospital()
    ensure_demo_data(db)
    duty = duty_schedule_today(db)
    department_id = duty.doctor.department_id

    available = client.get(f"/doctors/available?department_id={department_id}").json()
    booking = client.post(
        "/serials",
        json={
            "schedule_id": available[0]["schedule_id"],
            "patient_name": "Md. Rahim Uddin",
            "phone": "01712345678",
        },
    )

    assert booking.status_code == 201, booking.text
    assert booking.json()["serial_no"] == 9


def test_running_twice_creates_nothing_new(factory, db):
    factory.schedule(session=MORNING_SESSION)
    first = ensure_demo_data(db)
    counts = row_counts(db)

    second = ensure_demo_data(db)

    assert first.schedules_created > 0
    assert (second.duty_doctors_created, second.schedules_created, second.queues_created) == (
        0,
        0,
        0,
    )
    assert row_counts(db) == counts


def test_later_runs_fill_the_new_days_and_todays_queue(factory, db, monkeypatch):
    schedule = factory.schedule(session=MORNING_SESSION)
    ensure_demo_data(db)
    three_days_on = today_bd() + dt.timedelta(days=3)
    monkeypatch.setattr(demo_service, "today_bd", lambda: three_days_on)

    result = ensure_demo_data(db)

    # 3 new days of 2 doctor sessions and 1 duty session.
    assert result.schedules_created == 9
    assert result.queues_created == 1
    assert expected_sessions(three_days_on, MORNING_SESSION) <= sessions_of(db, schedule.doctor_id)
    assert (today_bd(), MORNING_SESSION[0]) in sessions_of(db, schedule.doctor_id)


def test_existing_schedules_and_serials_are_left_alone(factory, db):
    schedule = factory.schedule(
        session=(MORNING_SESSION[0], dt.time(10, 30)),
        max_serials=5,
        avg_minutes_per_patient=15,
        is_available=False,
    )
    [serial] = factory.queue(schedule, WAITING)
    updated_at = serial.updated_at

    ensure_demo_data(db)

    db.rollback()
    db.refresh(schedule)
    db.refresh(serial)
    assert schedule.end_time == dt.time(10, 30)
    assert (schedule.max_serials, schedule.avg_minutes_per_patient) == (5, 15)
    assert schedule.is_available is False
    assert (serial.status, serial.updated_at) == (WAITING, updated_at)


def test_duty_session_with_a_real_booking_gets_no_sample_queue(client, factory, db, monkeypatch):
    factory.hospital()
    tomorrow = today_bd() + dt.timedelta(days=1)
    ensure_demo_data(db)
    duty = duty_schedule_today(db, tomorrow)
    client.post(
        "/serials",
        json={"schedule_id": duty.id, "patient_name": "Md. Rahim Uddin", "phone": "01712345678"},
    )
    monkeypatch.setattr(demo_service, "today_bd", lambda: tomorrow)

    result = ensure_demo_data(db)

    assert result.queues_created == 0
    assert db.scalar(select(func.count(Serial.id)).where(Serial.schedule_id == duty.id)) == 1


def test_inactive_doctors_get_no_sessions(factory, db):
    schedule = factory.schedule(session=MORNING_SESSION, doctor_is_active=False)

    ensure_demo_data(db)

    assert sessions_of(db, schedule.doctor_id) == {(today_bd(), MORNING_SESSION[0])}


def test_demo_data_rolls_over_once_per_bangladesh_date(client, monkeypatch):
    calls = []
    today = today_bd()
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(demo_service, "_last_run_date", None)
    monkeypatch.setattr(demo_service, "ensure_demo_data", lambda db: calls.append(db))

    client.get("/hospitals")
    client.get("/doctors/available?department_id=99")
    assert len(calls) == 1

    monkeypatch.setattr(demo_service, "today_bd", lambda: today + dt.timedelta(days=1))
    client.get("/hospitals")
    client.get("/serials/99/status")
    assert len(calls) == 2


def test_demo_data_is_not_touched_when_demo_mode_is_off(client, monkeypatch):
    calls = []
    monkeypatch.setattr(demo_service, "_last_run_date", None)
    monkeypatch.setattr(demo_service, "ensure_demo_data", lambda db: calls.append(db))

    client.get("/hospitals")

    assert settings.demo_mode is False
    assert calls == []
