"""Reset the database and insert demo data.

WARNING: this drops every table in the target database, then recreates them.
Re-running is safe only because all existing data is thrown away.

The target is DEV_DATABASE_URL with --dev or APP_ENV=dev, otherwise DATABASE_URL.

Run with: python seed.py --dev
"""

import argparse
import datetime as dt
import os

if __name__ == "__main__":
    # Must run before the app imports below, which build the engine from APP_ENV.
    # argparse rejects a mistyped flag rather than seeding the main database.
    parser = argparse.ArgumentParser(description="Reset the database and insert demo data.")
    parser.add_argument("--dev", action="store_true", help="use the dev branch (same as APP_ENV=dev)")
    if parser.parse_args().dev:
        os.environ["APP_ENV"] = "dev"

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.time import today_bd  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Department,
    Doctor,
    DoctorSchedule,
    Hospital,
    Patient,
    Serial,
    SerialSource,
    SerialStatus,
    User,
    UserRole,
)

# Demo-only login shared by all seeded staff. Printed at the end of the run.
DEMO_PASSWORD = "Demo@1234"

SCHEDULE_START = dt.time(9, 0)
SCHEDULE_END = dt.time(13, 0)
SCHEDULE_MAX_SERIALS = 30

SUPER_ADMIN = ("Tanvir Ahmed", "01700000001")

HOSPITALS = [
    {
        "name": "Dhaka Medical College Hospital",
        "address": "Secretariat Road, Bakshibazar, Dhaka 1000",
        "district": "Dhaka",
        "admin": ("Sadia Rahman", "01700000011"),
        "staff": ("Imran Hossain", "01700000012"),
        "doctors": {
            "Medicine": [
                ("Dr. Mahmudul Hasan", "Internal Medicine"),
                ("Dr. Farzana Yasmin", "Diabetes and Endocrinology"),
            ],
            "Pediatrics": [
                ("Dr. Shafiqul Alam", "General Pediatrics"),
                ("Dr. Nusrat Jahan", "Neonatology"),
            ],
            "Gynecology": [
                ("Dr. Rokeya Sultana", "Obstetrics and Gynecology"),
                ("Dr. Tahmina Akter", "Maternal Health"),
            ],
        },
    },
    {
        "name": "Chattogram Medical College Hospital",
        "address": "K.B. Fazlul Kader Road, Panchlaish, Chattogram 4203",
        "district": "Chattogram",
        "admin": ("Jannatul Ferdous", "01800000011"),
        "staff": ("Rakib Uddin", "01800000012"),
        "doctors": {
            "Medicine": [
                ("Dr. Kamrul Islam", "Internal Medicine"),
                ("Dr. Sharmin Chowdhury", "Cardiology"),
            ],
            "Pediatrics": [
                ("Dr. Abdur Rahim", "General Pediatrics"),
                ("Dr. Mehnaz Karim", "Child Nutrition"),
            ],
            "Gynecology": [
                ("Dr. Salma Begum", "Obstetrics and Gynecology"),
                ("Dr. Afroza Khanam", "Maternal Health"),
            ],
        },
    },
]

# Serial numbers follow list order. Serial 4 is the patient being seen now.
SAMPLE_QUEUE = [
    ("Abdul Karim", "01900000001", SerialStatus.DONE, SerialSource.APP),
    ("Rahima Khatun", "01900000002", SerialStatus.DONE, SerialSource.SMS),
    ("Jamal Uddin", "01900000003", SerialStatus.MISSED, SerialSource.CALL),
    ("Shirin Akter", "01900000004", SerialStatus.SERVING, SerialSource.WALK_IN),
    ("Mizanur Rahman", "01900000005", SerialStatus.WAITING, SerialSource.APP),
    ("Hasina Parvin", "01900000006", SerialStatus.WAITING, SerialSource.WALK_IN),
    ("Nazmul Haque", "01900000007", SerialStatus.WAITING, SerialSource.SMS),
    ("Fatema Begum", "01900000008", SerialStatus.WAITING, SerialSource.APP),
]
CURRENT_SERIAL = 4

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def reset_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def build_hospital(data: dict) -> Hospital:
    """Build a hospital with its departments, doctors and schedules."""
    today = today_bd()
    schedule_dates = [today, today + dt.timedelta(days=1)]

    departments = [
        Department(
            name=department_name,
            doctors=[
                Doctor(
                    name=doctor_name,
                    specialty=specialty,
                    schedules=[
                        DoctorSchedule(
                            date=schedule_date,
                            start_time=SCHEDULE_START,
                            end_time=SCHEDULE_END,
                            max_serials=SCHEDULE_MAX_SERIALS,
                        )
                        for schedule_date in schedule_dates
                    ],
                )
                for doctor_name, specialty in doctors
            ],
        )
        for department_name, doctors in data["doctors"].items()
    ]
    return Hospital(
        name=data["name"],
        address=data["address"],
        district=data["district"],
        departments=departments,
    )


def build_user(
    name: str,
    phone: str,
    role: UserRole,
    hashed_password: str,
    hospital: Hospital | None = None,
) -> User:
    return User(
        name=name,
        phone=phone,
        role=role,
        hashed_password=hashed_password,
        hospital=hospital,
    )


def seed_queue(db: Session, schedule: DoctorSchedule, staff: User) -> None:
    """Fill one schedule with serials so the queue looks in progress."""
    for serial_no, (name, phone, status, source) in enumerate(SAMPLE_QUEUE, start=1):
        db.add(
            Serial(
                schedule=schedule,
                patient=Patient(name=name, phone=phone),
                serial_no=serial_no,
                status=status,
                source=source,
                creator=staff if source is SerialSource.WALK_IN else None,
            )
        )
    schedule.current_serial = CURRENT_SERIAL


def seed(db: Session) -> list[tuple[str, str, str]]:
    """Insert all demo data and return (role, hospital, phone) login rows."""
    hashed_password = pwd_context.hash(DEMO_PASSWORD)

    name, phone = SUPER_ADMIN
    db.add(build_user(name, phone, UserRole.SUPER_ADMIN, hashed_password))
    logins = [(UserRole.SUPER_ADMIN.value, "All hospitals", phone)]

    staff_by_hospital: list[User] = []
    hospitals: list[Hospital] = []
    for data in HOSPITALS:
        hospital = build_hospital(data)
        db.add(hospital)
        hospitals.append(hospital)

        admin_name, admin_phone = data["admin"]
        staff_name, staff_phone = data["staff"]
        admin = build_user(
            admin_name, admin_phone, UserRole.HOSPITAL_ADMIN, hashed_password, hospital
        )
        staff = build_user(staff_name, staff_phone, UserRole.STAFF, hashed_password, hospital)
        db.add_all([admin, staff])
        staff_by_hospital.append(staff)

        logins.append((UserRole.HOSPITAL_ADMIN.value, hospital.name, admin_phone))
        logins.append((UserRole.STAFF.value, hospital.name, staff_phone))

    # First doctor of the first hospital's first department, today's schedule.
    todays_schedule = hospitals[0].departments[0].doctors[0].schedules[0]
    seed_queue(db, todays_schedule, staff_by_hospital[0])

    return logins


def print_logins(logins: list[tuple[str, str, str]]) -> None:
    print(f"\nDemo logins (password for all: {DEMO_PASSWORD})")
    print(f"{'Role':<16} {'Phone':<13} Hospital")
    print("-" * 66)
    for role, hospital, phone in logins:
        print(f"{role:<16} {phone:<13} {hospital}")


def main() -> None:
    print(f"Target database: {settings.database_target}")
    print("Dropping and recreating all tables...")
    reset_tables()

    with SessionLocal.begin() as db:
        logins = seed(db)

    print("Seed data inserted.")
    print_logins(logins)


if __name__ == "__main__":
    main()
