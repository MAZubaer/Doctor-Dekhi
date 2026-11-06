"""Keeps the deployed demo usable on any day.

Only DEMO_MODE runs this automatically. It adds rows and never deletes anything,
and it never changes a schedule that already exists, apart from starting the sample
queue on a duty session that has no serials.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from threading import Lock

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.time import today_bd
from app.database import SessionLocal, transaction
from app.models import (
    Department,
    Doctor,
    DoctorSchedule,
    Hospital,
    Patient,
    Serial,
    SerialSource,
    SerialStatus,
)
from app.services.serial_service import lock_schedule

logger = logging.getLogger(__name__)

MORNING_SESSION = (dt.time(9, 0), dt.time(13, 0))
EVENING_SESSION = (dt.time(16, 0), dt.time(23, 30))
# Ends at the last second of the day, so today always has an open session.
DUTY_SESSION = (dt.time(0, 0), dt.time(23, 59, 59))

DEMO_DAYS = 7
SCHEDULE_MAX_SERIALS = 30
DUTY_MAX_SERIALS = 100

DUTY_DEPARTMENT = "Emergency"
DUTY_SPECIALTY = "Emergency Duty"
DUTY_DOCTOR_NAMES = ["Dr. Ayesha Siddika", "Dr. Mostafizur Rahman"]

# Serial numbers follow list order. Phone numbers are built from the hospital ID.
SAMPLE_QUEUE = [
    ("Abul Kalam", SerialStatus.DONE, SerialSource.APP),
    ("Nasima Begum", SerialStatus.DONE, SerialSource.SMS),
    ("Harun Mia", SerialStatus.MISSED, SerialSource.CALL),
    ("Sumaiya Islam", SerialStatus.SERVING, SerialSource.APP),
    ("Delwar Hossain", SerialStatus.WAITING, SerialSource.CALL),
    ("Moriom Khatun", SerialStatus.WAITING, SerialSource.APP),
    ("Selim Reza", SerialStatus.WAITING, SerialSource.SMS),
    ("Parveen Sultana", SerialStatus.WAITING, SerialSource.APP),
]

# Any fixed number works, as long as every run uses the same one.
DEMO_LOCK_ID = 7_260_001

_last_run_date: dt.date | None = None
_run_lock = Lock()


@dataclass
class DemoDataResult:
    duty_doctors_created: int
    schedules_created: int
    queues_created: int


def ensure_demo_data(db: Session) -> DemoDataResult:
    """Add whatever is missing for the next DEMO_DAYS days. Safe to run many times."""
    today = today_bd()
    with transaction(db):
        # Held until commit, so two overlapping runs cannot both add a duty doctor.
        db.execute(select(func.pg_advisory_xact_lock(DEMO_LOCK_ID)))
        hospitals = db.scalars(select(Hospital).order_by(Hospital.id)).all()
        duty_doctors_created = sum(_ensure_duty_doctor(db, hospital) for hospital in hospitals)
        schedules_created = _ensure_schedules(db, today)
        queues_created = sum(_ensure_duty_queue(db, hospital, today) for hospital in hospitals)

    return DemoDataResult(duty_doctors_created, schedules_created, queues_created)


def keep_demo_data_current() -> None:
    """Run ensure_demo_data once per Bangladesh date while DEMO_MODE is on.

    A failed run is logged and retried on the next request, so a database problem
    here never takes down a request that might have worked.
    """
    global _last_run_date
    if not settings.demo_mode:
        return
    today = today_bd()
    if _last_run_date == today:
        return

    with _run_lock:
        if _last_run_date == today:
            return
        try:
            with SessionLocal() as db:
                result = ensure_demo_data(db)
        except SQLAlchemyError as exc:
            logger.error("Demo data could not be updated: %s", type(exc).__name__)
            return
        _last_run_date = today
    logger.info("Demo data is current for %s: %s", today, result)


def _ensure_duty_doctor(db: Session, hospital: Hospital) -> bool:
    """Create the hospital's Emergency department and duty doctor if either is missing."""
    department = db.scalar(
        select(Department).where(
            Department.hospital_id == hospital.id,
            Department.name == DUTY_DEPARTMENT,
        )
    )
    if department is None:
        department = Department(hospital_id=hospital.id, name=DUTY_DEPARTMENT)
        db.add(department)
        db.flush()

    has_duty_doctor = db.scalar(
        select(
            exists().where(
                Doctor.department_id == department.id,
                Doctor.specialty == DUTY_SPECIALTY,
            )
        )
    )
    if has_duty_doctor:
        return False

    name = DUTY_DOCTOR_NAMES[hospital.id % len(DUTY_DOCTOR_NAMES)]
    db.add(Doctor(department_id=department.id, name=name, specialty=DUTY_SPECIALTY))
    db.flush()
    return True


def _ensure_schedules(db: Session, today: dt.date) -> int:
    """Insert missing sessions. The unique constraint leaves existing ones untouched."""
    days = [today + dt.timedelta(days=offset) for offset in range(DEMO_DAYS)]
    rows = []
    for doctor_id, specialty in db.execute(
        select(Doctor.id, Doctor.specialty).where(Doctor.is_active)
    ):
        is_duty_doctor = specialty == DUTY_SPECIALTY
        sessions = [DUTY_SESSION] if is_duty_doctor else [MORNING_SESSION, EVENING_SESSION]
        max_serials = DUTY_MAX_SERIALS if is_duty_doctor else SCHEDULE_MAX_SERIALS
        rows += [
            {
                "doctor_id": doctor_id,
                "date": day,
                "start_time": start_time,
                "end_time": end_time,
                "max_serials": max_serials,
            }
            for day in days
            for start_time, end_time in sessions
        ]
    if not rows:
        return 0

    created = db.scalars(
        insert(DoctorSchedule)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_doctor_schedules_doctor_date_start")
        .returning(DoctorSchedule.id)
    ).all()
    return len(created)


def _ensure_duty_queue(db: Session, hospital: Hospital, today: dt.date) -> bool:
    """Start a sample queue on today's duty session if it has no serials yet."""
    schedule = db.scalar(
        select(DoctorSchedule)
        .join(DoctorSchedule.doctor)
        .join(Doctor.department)
        .where(
            Department.hospital_id == hospital.id,
            Doctor.specialty == DUTY_SPECIALTY,
            DoctorSchedule.date == today,
            DoctorSchedule.start_time == DUTY_SESSION[0],
        )
        .limit(1)
    )
    if schedule is None:
        return False

    # Locked first, so a patient booking right now cannot get the same serial number.
    lock_schedule(db, schedule.id)
    if db.scalar(select(exists().where(Serial.schedule_id == schedule.id))):
        return False

    phones = [f"0191{hospital.id:03d}{number:04d}" for number in range(1, len(SAMPLE_QUEUE) + 1)]
    db.execute(
        insert(Patient)
        .values(
            [
                {"name": name, "phone": phone}
                for phone, (name, _, _) in zip(phones, SAMPLE_QUEUE)
            ]
        )
        .on_conflict_do_nothing(index_elements=[Patient.phone])
    )
    patient_ids = dict(
        db.execute(select(Patient.phone, Patient.id).where(Patient.phone.in_(phones))).all()
    )

    for serial_no, (phone, (_, status, source)) in enumerate(zip(phones, SAMPLE_QUEUE), start=1):
        db.add(
            Serial(
                schedule_id=schedule.id,
                patient_id=patient_ids[phone],
                serial_no=serial_no,
                status=status,
                source=source,
            )
        )
        if status is SerialStatus.SERVING:
            schedule.current_serial = serial_no
    return True
