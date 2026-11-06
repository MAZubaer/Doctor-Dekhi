"""Doctor availability."""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from app.core.errors import BadRequestError, NotFoundError
from app.core.time import now_bd
from app.models import Department, Doctor, DoctorSchedule, Serial
from app.schemas.doctor import AvailableDoctorOut


def list_available(
    db: Session,
    department_id: int,
    date: dt.date | None = None,
) -> list[AvailableDoctorOut]:
    """List schedules that can still be booked in a department on a date."""
    now = now_bd()
    date = date or now.date()
    if date < now.date():
        raise BadRequestError("DATE_IN_PAST", "Date cannot be in the past.")

    if db.get(Department, department_id) is None:
        raise NotFoundError(
            "DEPARTMENT_NOT_FOUND",
            f"Department {department_id} was not found.",
        )

    query = (
        select(DoctorSchedule, func.count(Serial.id))
        .join(DoctorSchedule.doctor)
        .outerjoin(DoctorSchedule.serials)
        .options(contains_eager(DoctorSchedule.doctor))
        .where(
            Doctor.department_id == department_id,
            Doctor.is_active,
            DoctorSchedule.is_available,
            DoctorSchedule.date == date,
        )
        .group_by(DoctorSchedule.id, Doctor.id)
        .order_by(Doctor.name, DoctorSchedule.start_time)
    )
    # A session that has already ended today cannot be booked, so hide it.
    if date == now.date():
        query = query.where(DoctorSchedule.end_time > now.time())

    return [
        AvailableDoctorOut(
            doctor_id=schedule.doctor.id,
            doctor_name=schedule.doctor.name,
            specialty=schedule.doctor.specialty,
            schedule_id=schedule.id,
            date=schedule.date,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            serials_booked=booked,
            serials_left=max(schedule.max_serials - booked, 0),
        )
        for schedule, booked in db.execute(query)
    ]
