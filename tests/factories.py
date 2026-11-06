"""Small builders for test data, and helpers shared by the test files."""

import datetime as dt
from itertools import count

from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.time import today_bd
from app.models import (
    Department,
    Doctor,
    DoctorSchedule,
    Hospital,
    Notification,
    NotificationType,
    Patient,
    Serial,
    SerialStatus,
    User,
    UserRole,
)

PASSWORD = "Test@1234"
# Hashing is slow on purpose, so every test user shares one hash.
PASSWORD_HASH = hash_password(PASSWORD)

WHOLE_DAY = (dt.time(0, 0), dt.time(23, 59, 59))

WAITING = SerialStatus.WAITING
SERVING = SerialStatus.SERVING
DONE = SerialStatus.DONE
MISSED = SerialStatus.MISSED


class Factory:
    """Create only the rows a test needs, committed so the API can see them."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._numbers = count(1)

    def phone(self) -> str:
        return f"017{next(self._numbers):08d}"

    def hospital(self, name: str = "Dhaka Medical College Hospital") -> Hospital:
        hospital = Hospital(name=name, district="Dhaka")
        self.db.add(hospital)
        self.db.commit()
        return hospital

    def schedule(
        self,
        hospital: Hospital | None = None,
        date: dt.date | None = None,
        session: tuple[dt.time, dt.time] = WHOLE_DAY,
        max_serials: int = 30,
        avg_minutes_per_patient: int = 10,
        is_available: bool = True,
        doctor_is_active: bool = True,
    ) -> DoctorSchedule:
        """Create a schedule for today, with its own department and doctor."""
        start_time, end_time = session
        schedule = DoctorSchedule(
            date=date or today_bd(),
            start_time=start_time,
            end_time=end_time,
            max_serials=max_serials,
            avg_minutes_per_patient=avg_minutes_per_patient,
            is_available=is_available,
            doctor=Doctor(
                name="Dr. Mahmudul Hasan",
                is_active=doctor_is_active,
                department=Department(
                    name=f"Medicine {next(self._numbers)}",
                    hospital=hospital or self.hospital(),
                ),
            ),
        )
        self.db.add(schedule)
        self.db.commit()
        return schedule

    def user(
        self,
        role: UserRole,
        hospital: Hospital | None = None,
        is_active: bool = True,
    ) -> User:
        user = User(
            name="Imran Hossain",
            phone=self.phone(),
            role=role,
            hashed_password=PASSWORD_HASH,
            hospital=hospital,
            is_active=is_active,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def queue(self, schedule: DoctorSchedule, *statuses: SerialStatus) -> list[Serial]:
        """Add serials numbered from 1, and point current_serial at the one being served."""
        serials = [
            Serial(
                schedule=schedule,
                patient=Patient(name="Abdul Karim", phone=self.phone()),
                serial_no=serial_no,
                status=status,
            )
            for serial_no, status in enumerate(statuses, start=1)
        ]
        self.db.add_all(serials)
        for serial in serials:
            if serial.status is SERVING:
                schedule.current_serial = serial.serial_no
        self.db.commit()
        return serials


def assert_error(response: Response, status_code: int, error: str) -> dict:
    """Check a response is this error in the API's one error shape, and return its body."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error", "message", "details"}
    assert body["error"] == error
    assert isinstance(body["message"], str) and body["message"]
    return body


def serial_nos_notified(
    db: Session,
    schedule: DoctorSchedule,
    notification_type: NotificationType,
) -> list[int]:
    """List the serial number of each notification of a type, including any repeats."""
    db.rollback()  # Ends the read snapshot, so rows committed by the API are visible.
    return list(
        db.scalars(
            select(Serial.serial_no)
            .join(Notification, Notification.serial_id == Serial.id)
            .where(Serial.schedule_id == schedule.id, Notification.type == notification_type)
            .order_by(Serial.serial_no)
        )
    )
