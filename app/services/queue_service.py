"""Live queue status for a serial."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import NotFoundError
from app.models import Department, Doctor, DoctorSchedule, Serial, SerialStatus
from app.schemas.serial import QueueStatusOut

STATUS_MESSAGES = {
    SerialStatus.SERVING: "It's your turn now.",
    SerialStatus.DONE: "Visit completed.",
    SerialStatus.MISSED: "You missed your turn. Please speak to the hospital staff.",
}


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

    is_waiting = serial.status is SerialStatus.WAITING
    people_ahead = _count_waiting_ahead(db, serial) if is_waiting else 0
    message = (
        _waiting_message(people_ahead) if is_waiting else STATUS_MESSAGES[serial.status]
    )

    return QueueStatusOut(
        serial_id=serial.id,
        serial_no=serial.serial_no,
        status=serial.status,
        now_serving=schedule.current_serial,
        people_ahead=people_ahead,
        estimated_wait_minutes=people_ahead * schedule.avg_minutes_per_patient,
        message=message,
        doctor_name=schedule.doctor.name,
        department_name=department.name,
        hospital_name=department.hospital.name,
        schedule_date=schedule.date,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
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


def _waiting_message(people_ahead: int) -> str:
    if people_ahead == 0:
        return "You are next in the queue."
    noun = "person" if people_ahead == 1 else "people"
    return f"{people_ahead} {noun} ahead of you."
