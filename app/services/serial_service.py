"""Serial booking, shared by patient bookings and staff walk-ins."""

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.phone import mask_phone
from app.core.time import now_bd, today_bd
from app.models import (
    DoctorSchedule,
    Notification,
    NotificationType,
    Patient,
    Serial,
    SerialSource,
    SerialStatus,
)
from app.schemas.serial import SerialCreate

logger = logging.getLogger(__name__)

MAX_BOOKING_ATTEMPTS = 2
ACTIVE_STATUSES = (SerialStatus.WAITING, SerialStatus.SERVING)


def book_serial(
    db: Session,
    data: SerialCreate,
    source: SerialSource = SerialSource.APP,
    created_by: int | None = None,
) -> Serial:
    """Book the next serial on a schedule and record a mock confirmation SMS.

    Everything happens in one transaction. An IntegrityError means a concurrent
    request won a race, on the serial number or on creating the same new patient,
    so the booking is retried once from the start.
    """
    for _ in range(MAX_BOOKING_ATTEMPTS):
        try:
            serial, notification = _create_serial(db, data, source, created_by)
            db.commit()
        except IntegrityError:
            db.rollback()
        except Exception:
            db.rollback()
            raise
        else:
            # Logged after the commit so a rolled-back booking sends no SMS.
            log_mock_sms(notification)
            return serial

    raise ConflictError(
        "BOOKING_CONFLICT",
        "Too many people are booking this schedule right now. Please try again.",
    )


def lock_schedule(db: Session, schedule_id: int) -> None:
    """Hold a row lock until commit so changes to one queue run one at a time.

    The row must be fetched, not only selected: populate_existing refreshes a loaded
    schedule when its row is read, and callers rely on seeing the latest values.
    """
    db.scalar(
        select(DoctorSchedule)
        .where(DoctorSchedule.id == schedule_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def log_mock_sms(notification: Notification) -> None:
    logger.info("Mock SMS to %s: %s", mask_phone(notification.phone), notification.message)


def _create_serial(
    db: Session,
    data: SerialCreate,
    source: SerialSource,
    created_by: int | None,
) -> tuple[Serial, Notification]:
    schedule = _get_schedule(db, data.schedule_id)
    _ensure_doctor_available(schedule)
    _ensure_schedule_open(schedule)
    patient = _find_or_create_patient(db, data)
    _ensure_not_booked(db, schedule.id, patient.id)

    lock_schedule(db, schedule.id)
    # Checked again now that the lock is held: the schedule may have been cancelled,
    # and two simultaneous requests from one patient can both pass the check above.
    _ensure_doctor_available(schedule)
    _ensure_not_booked(db, schedule.id, patient.id)
    serial_no = _next_serial_no(db, schedule)

    serial = Serial(
        schedule=schedule,
        patient=patient,
        serial_no=serial_no,
        status=SerialStatus.WAITING,
        source=source,
        created_by=created_by,
    )
    notification = Notification(
        serial=serial,
        phone=patient.phone,
        message=_confirmation_message(serial_no, schedule),
        type=NotificationType.CONFIRMATION,
    )
    db.add_all([serial, notification])
    return serial, notification


def _get_schedule(db: Session, schedule_id: int) -> DoctorSchedule:
    schedule = db.get(
        DoctorSchedule,
        schedule_id,
        options=[joinedload(DoctorSchedule.doctor)],
    )
    if schedule is None:
        raise NotFoundError(
            "SCHEDULE_NOT_FOUND",
            f"Schedule {schedule_id} was not found.",
        )
    return schedule


def _ensure_doctor_available(schedule: DoctorSchedule) -> None:
    if not schedule.doctor.is_active or not schedule.is_available:
        raise BadRequestError(
            "DOCTOR_UNAVAILABLE",
            "This doctor is not available for this schedule.",
        )


def _ensure_schedule_open(schedule: DoctorSchedule) -> None:
    now = now_bd()
    is_past_date = schedule.date < now.date()
    has_ended_today = schedule.date == now.date() and schedule.end_time <= now.time()
    if is_past_date or has_ended_today:
        raise BadRequestError(
            "SCHEDULE_CLOSED",
            "This schedule has ended and can no longer be booked.",
        )


def _find_or_create_patient(db: Session, data: SerialCreate) -> Patient:
    """Return the patient with this phone. An existing name is left unchanged."""
    patient = db.scalar(select(Patient).where(Patient.phone == data.phone))
    if patient is None:
        patient = Patient(name=data.patient_name, phone=data.phone)
        db.add(patient)
        db.flush()
    return patient


def _ensure_not_booked(db: Session, schedule_id: int, patient_id: int) -> None:
    existing = db.scalar(
        select(Serial).where(
            Serial.schedule_id == schedule_id,
            Serial.patient_id == patient_id,
            Serial.status.in_(ACTIVE_STATUSES),
        )
    )
    if existing is not None:
        raise ConflictError(
            "ALREADY_BOOKED",
            f"This patient already has serial #{existing.serial_no} on this schedule.",
            {"serial_id": existing.id, "serial_no": existing.serial_no},
        )


def _next_serial_no(db: Session, schedule: DoctorSchedule) -> int:
    booked, last_serial_no = db.execute(
        select(func.count(Serial.id), func.coalesce(func.max(Serial.serial_no), 0)).where(
            Serial.schedule_id == schedule.id
        )
    ).one()
    if booked >= schedule.max_serials:
        raise ConflictError(
            "SCHEDULE_FULL",
            "No serials left for this doctor on this schedule.",
        )
    return last_serial_no + 1


def _confirmation_message(serial_no: int, schedule: DoctorSchedule) -> str:
    day = "today" if schedule.date == today_bd() else schedule.date.strftime("%d %b %Y")
    time = schedule.start_time.strftime("%I:%M %p").lstrip("0")
    return f"Doctor Dekhi: Your serial is #{serial_no} with {schedule.doctor.name}, {day} {time}."
