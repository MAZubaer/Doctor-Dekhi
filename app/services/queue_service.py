"""Live queue status and the staff actions that move a queue forward."""

import datetime as dt
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.deps import ensure_hospital_access
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.time import today_bd
from app.database import transaction
from app.models import (
    Department,
    Doctor,
    DoctorSchedule,
    Hospital,
    Notification,
    NotificationType,
    Serial,
    SerialSource,
    SerialStatus,
    User,
    UserRole,
)
from app.schemas.serial import QueueStatusOut, SerialCreate, SerialOut, WalkInCreate
from app.schemas.staff import (
    AvailabilityOut,
    CallNextOut,
    QueueCounts,
    QueueEntryOut,
    ScheduleSummaryOut,
)
from app.services.serial_service import book_serial, lock_schedule, log_mock_sms

logger = logging.getLogger(__name__)

# The only place that decides how a serial's status may change.
ALLOWED_TRANSITIONS = {
    SerialStatus.WAITING: {SerialStatus.SERVING, SerialStatus.MISSED},
    SerialStatus.SERVING: {SerialStatus.DONE, SerialStatus.MISSED},
}

STATUS_MESSAGES = {
    SerialStatus.SERVING: "It's your turn now.",
    SerialStatus.DONE: "Visit completed.",
    SerialStatus.MISSED: "You missed your turn. Please speak to the hospital staff.",
}
ON_HOLD_MESSAGE = "Doctor is unavailable right now. Your serial is on hold."


def get_status(db: Session, serial_id: int) -> QueueStatusOut:
    serial = db.get(
        Serial,
        serial_id,
        options=[
            joinedload(Serial.schedule)
            .joinedload(DoctorSchedule.doctor)
            .joinedload(Doctor.department)
            .joinedload(Department.hospital)
        ],
    )
    if serial is None:
        raise NotFoundError("SERIAL_NOT_FOUND", f"Serial {serial_id} was not found.")

    schedule = serial.schedule
    department = schedule.doctor.department

    people_ahead = 0
    wait_minutes = 0
    message = STATUS_MESSAGES.get(serial.status)
    is_on_hold = serial.status is SerialStatus.WAITING and not schedule.is_available
    if serial.status is SerialStatus.WAITING:
        people_ahead = _count_waiting_ahead(db, serial)
        patients_before_turn = people_ahead + _serving_count(db, schedule.id)
        wait_minutes = patients_before_turn * schedule.avg_minutes_per_patient
        message = _waiting_message(people_ahead)
    if is_on_hold:
        wait_minutes = None
        message = ON_HOLD_MESSAGE

    return QueueStatusOut(
        serial_id=serial.id,
        serial_no=serial.serial_no,
        status=serial.status,
        now_serving=schedule.current_serial,
        people_ahead=people_ahead,
        estimated_wait_minutes=wait_minutes,
        is_on_hold=is_on_hold,
        message=message,
        doctor_name=schedule.doctor.name,
        department_name=department.name,
        hospital_name=department.hospital.name,
        schedule_date=schedule.date,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
    )


def call_next(
    db: Session,
    schedule: DoctorSchedule,
    user: User,
    expected_current_serial: int | None = None,
) -> CallNextOut:
    """Finish the patient being served and move the next waiting patient up."""
    with transaction(db):
        lock_schedule(db, schedule.id)
        _ensure_schedule_active(schedule)
        _ensure_queue_unchanged(schedule, expected_current_serial)

        finished = _first_with_status(db, schedule.id, SerialStatus.SERVING)
        serving = _first_with_status(db, schedule.id, SerialStatus.WAITING)
        if finished is None and serving is None:
            raise BadRequestError("QUEUE_EMPTY", "There are no patients in this queue.")

        if finished is not None:
            _change_status(finished, SerialStatus.DONE)

        turn_near: list[Notification] = []
        if serving is not None:
            _change_status(serving, SerialStatus.SERVING)
            schedule.current_serial = serving.serial_no
            turn_near = _create_turn_near_notifications(db, schedule)

        message = (
            f"Now serving serial #{serving.serial_no}."
            if serving is not None
            else "Queue finished. No patients are waiting."
        )
        result = CallNextOut(
            message=message,
            finished_serial=SerialOut.from_serial(finished) if finished else None,
            serving_serial=SerialOut.from_serial(serving) if serving else None,
            current_serial=schedule.current_serial,
            counts=_count_by_status(db, schedule.id),
        )

    for notification in turn_near:
        log_mock_sms(notification)
    logger.info("User %s called next on schedule %s: %s", user.id, schedule.id, message)
    return result


def mark_missed(db: Session, serial: Serial, user: User) -> Serial:
    with transaction(db):
        lock_schedule(db, serial.schedule_id)
        # The status may have changed while waiting for the lock.
        db.refresh(serial)
        _change_status(serial, SerialStatus.MISSED)

    logger.info("User %s marked serial %s as missed", user.id, serial.id)
    return serial


def add_walk_in(
    db: Session,
    schedule: DoctorSchedule,
    data: WalkInCreate,
    user: User,
) -> Serial:
    booking = SerialCreate(schedule_id=schedule.id, **data.model_dump())
    return book_serial(db, booking, source=SerialSource.WALK_IN, created_by=user.id)


def set_availability(
    db: Session,
    schedule: DoctorSchedule,
    is_available: bool,
    user: User,
) -> AvailabilityOut:
    """Open or close a schedule, telling waiting patients when it is cancelled."""
    with transaction(db):
        lock_schedule(db, schedule.id)
        is_being_cancelled = schedule.is_available and not is_available
        schedule.is_available = is_available
        notifications = _create_cancelled_notifications(db, schedule) if is_being_cancelled else []

    for notification in notifications:
        log_mock_sms(notification)
    logger.info("User %s set schedule %s available=%s", user.id, schedule.id, is_available)
    return AvailabilityOut(
        schedule_id=schedule.id,
        is_available=is_available,
        patients_notified=len(notifications),
    )


def list_schedules(
    db: Session,
    user: User,
    date: dt.date | None = None,
    hospital_id: int | None = None,
) -> list[ScheduleSummaryOut]:
    """List schedules with queue counts, limited to the hospitals the user can see."""
    date = date or today_bd()
    hospital_filter = _resolve_hospital_filter(db, user, hospital_id)

    def count_with(status: SerialStatus):
        return func.count(Serial.id).filter(Serial.status == status)

    query = (
        select(
            DoctorSchedule,
            Doctor.name,
            Department.name,
            Hospital.name,
            count_with(SerialStatus.WAITING),
            count_with(SerialStatus.SERVING),
            count_with(SerialStatus.DONE),
            count_with(SerialStatus.MISSED),
        )
        .join(DoctorSchedule.doctor)
        .join(Doctor.department)
        .join(Department.hospital)
        .outerjoin(DoctorSchedule.serials)
        .where(DoctorSchedule.date == date)
        .group_by(DoctorSchedule.id, Doctor.id, Department.id, Hospital.id)
        .order_by(Hospital.name, Department.name, Doctor.name, DoctorSchedule.start_time)
    )
    if hospital_filter is not None:
        query = query.where(Department.hospital_id == hospital_filter)

    return [
        ScheduleSummaryOut(
            schedule_id=schedule.id,
            doctor_name=doctor_name,
            department_name=department_name,
            hospital_name=hospital_name,
            date=schedule.date,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            is_available=schedule.is_available,
            max_serials=schedule.max_serials,
            current_serial=schedule.current_serial,
            counts=QueueCounts(waiting=waiting, serving=serving, done=done, missed=missed),
        )
        for schedule, doctor_name, department_name, hospital_name, waiting, serving, done, missed
        in db.execute(query)
    ]


def get_queue(db: Session, schedule: DoctorSchedule) -> list[QueueEntryOut]:
    serials = db.scalars(
        select(Serial)
        .options(joinedload(Serial.patient))
        .where(Serial.schedule_id == schedule.id)
        .order_by(Serial.serial_no)
    )
    return [
        QueueEntryOut(
            id=serial.id,
            serial_no=serial.serial_no,
            status=serial.status,
            source=serial.source,
            patient_name=serial.patient.name,
            phone=serial.patient.phone,
            created_by=serial.created_by,
            created_at=serial.created_at,
        )
        for serial in serials
    ]


def _change_status(serial: Serial, new_status: SerialStatus) -> None:
    if new_status not in ALLOWED_TRANSITIONS.get(serial.status, ()):
        raise BadRequestError(
            "INVALID_STATUS_TRANSITION",
            f"A serial that is {serial.status.value} cannot become {new_status.value}.",
            {"from": serial.status.value, "to": new_status.value},
        )
    serial.status = new_status


def _ensure_schedule_active(schedule: DoctorSchedule) -> None:
    if schedule.date != today_bd() or not schedule.is_available:
        raise BadRequestError(
            "SCHEDULE_NOT_ACTIVE",
            "Patients can only be called on an available schedule for today.",
        )


def _ensure_queue_unchanged(schedule: DoctorSchedule, expected_current_serial: int | None) -> None:
    """Stop a repeated click from calling a second patient by accident."""
    if expected_current_serial is None or expected_current_serial == schedule.current_serial:
        return
    raise ConflictError(
        "QUEUE_CHANGED",
        f"The queue has moved on. The current serial is #{schedule.current_serial}.",
        {
            "expected_current_serial": expected_current_serial,
            "current_serial": schedule.current_serial,
        },
    )


def _resolve_hospital_filter(db: Session, user: User, hospital_id: int | None) -> int | None:
    """Return the hospital to filter by. None means every hospital."""
    if user.role is not UserRole.SUPER_ADMIN:
        if hospital_id is not None:
            ensure_hospital_access(user, hospital_id)
        return user.hospital_id

    if hospital_id is not None and db.get(Hospital, hospital_id) is None:
        raise NotFoundError("HOSPITAL_NOT_FOUND", f"Hospital {hospital_id} was not found.")
    return hospital_id


def _first_with_status(db: Session, schedule_id: int, status: SerialStatus) -> Serial | None:
    return db.scalar(
        select(Serial)
        .where(Serial.schedule_id == schedule_id, Serial.status == status)
        .order_by(Serial.serial_no)
        .limit(1)
    )


def _create_turn_near_notifications(db: Session, schedule: DoctorSchedule) -> list[Notification]:
    """Warn waiting patients within TURN_NEAR_POSITION places, once per serial.

    The caller holds the schedule lock, so two calls cannot both send to one serial.
    """
    nearest = db.scalars(
        select(Serial)
        .options(joinedload(Serial.patient))
        .where(Serial.schedule_id == schedule.id, Serial.status == SerialStatus.WAITING)
        .order_by(Serial.serial_no)
        .limit(settings.turn_near_position)
    ).all()
    already_warned = set(
        db.scalars(
            select(Notification.serial_id).where(
                Notification.serial_id.in_([serial.id for serial in nearest]),
                Notification.type == NotificationType.TURN_NEAR,
            )
        )
    )
    notifications = [
        Notification(
            serial=serial,
            phone=serial.patient.phone,
            message=(
                f"Doctor Dekhi: Your turn is near. Serial #{serial.serial_no} "
                f"with {schedule.doctor.name}. Please stay close."
            ),
            type=NotificationType.TURN_NEAR,
        )
        for serial in nearest
        if serial.id not in already_warned
    ]
    db.add_all(notifications)
    return notifications


def _create_cancelled_notifications(db: Session, schedule: DoctorSchedule) -> list[Notification]:
    waiting = db.scalars(
        select(Serial)
        .options(joinedload(Serial.patient))
        .where(Serial.schedule_id == schedule.id, Serial.status == SerialStatus.WAITING)
        .order_by(Serial.serial_no)
    ).all()
    day = schedule.date.strftime("%d %b %Y")
    notifications = [
        Notification(
            serial=serial,
            phone=serial.patient.phone,
            message=(
                f"Doctor Dekhi: {schedule.doctor.name}'s session on {day} is cancelled. "
                f"This affects your serial #{serial.serial_no}."
            ),
            type=NotificationType.CANCELLED,
        )
        for serial in waiting
    ]
    db.add_all(notifications)
    return notifications


def _count_by_status(db: Session, schedule_id: int) -> QueueCounts:
    rows = db.execute(
        select(Serial.status, func.count(Serial.id))
        .where(Serial.schedule_id == schedule_id)
        .group_by(Serial.status)
    ).all()
    counts = {status: count for status, count in rows}
    return QueueCounts(
        waiting=counts.get(SerialStatus.WAITING, 0),
        serving=counts.get(SerialStatus.SERVING, 0),
        done=counts.get(SerialStatus.DONE, 0),
        missed=counts.get(SerialStatus.MISSED, 0),
    )


def _count_waiting_ahead(db: Session, serial: Serial) -> int:
    """Count only WAITING serials, so missed patients do not add to the wait."""
    return db.scalar(
        select(func.count(Serial.id)).where(
            Serial.schedule_id == serial.schedule_id,
            Serial.status == SerialStatus.WAITING,
            Serial.serial_no < serial.serial_no,
        )
    )


def _serving_count(db: Session, schedule_id: int) -> int:
    return db.scalar(
        select(func.count(Serial.id)).where(
            Serial.schedule_id == schedule_id,
            Serial.status == SerialStatus.SERVING,
        )
    )


def _waiting_message(people_ahead: int) -> str:
    if people_ahead == 0:
        return "You are next in the queue."
    noun = "person" if people_ahead == 1 else "people"
    return f"{people_ahead} {noun} ahead of you."
