"""SQLAlchemy models and enums for the hospital serial and queue system."""

import datetime as dt
from enum import StrEnum
from typing import Annotated

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SerialStatus(StrEnum):
    WAITING = "waiting"
    SERVING = "serving"
    DONE = "done"
    MISSED = "missed"


class SerialSource(StrEnum):
    APP = "app"
    SMS = "sms"
    CALL = "call"
    WALK_IN = "walk_in"


class UserRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    HOSPITAL_ADMIN = "hospital_admin"
    STAFF = "staff"


class NotificationType(StrEnum):
    CONFIRMATION = "confirmation"
    TURN_NEAR = "turn_near"
    CANCELLED = "cancelled"


class NotificationStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


def enum_type(enum_class: type[StrEnum], name: str) -> Enum:
    """Build a column type that stores enum values, such as 'super_admin'.

    SQLAlchemy stores member names by default ('SUPER_ADMIN'), which would not
    match the values used in CHECK constraints and API responses.
    """
    return Enum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
    )


CreatedAt = Annotated[
    dt.datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now()),
]
UpdatedAt = Annotated[
    dt.datetime,
    mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    ),
]


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(255))
    district: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[CreatedAt]

    departments: Mapped[list["Department"]] = relationship(back_populates="hospital")
    users: Mapped[list["User"]] = relationship(back_populates="hospital")


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("hospital_id", "name", name="uq_departments_hospital_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id"))
    name: Mapped[str] = mapped_column(String(100))

    hospital: Mapped["Hospital"] = relationship(back_populates="departments")
    doctors: Mapped[list["Doctor"]] = relationship(back_populates="department")


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    name: Mapped[str] = mapped_column(String(120))
    specialty: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(server_default=true())

    department: Mapped["Department"] = relationship(back_populates="doctors")
    schedules: Mapped[list["DoctorSchedule"]] = relationship(back_populates="doctor")


class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"
    __table_args__ = (
        UniqueConstraint(
            "doctor_id", "date", "start_time", name="uq_doctor_schedules_doctor_date_start"
        ),
        CheckConstraint("end_time > start_time", name="ck_doctor_schedules_end_after_start"),
        CheckConstraint("max_serials > 0", name="ck_doctor_schedules_max_serials_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    # dt.date, not a bare `date`: the attribute would shadow the type in this class.
    date: Mapped[dt.date] = mapped_column(index=True)
    start_time: Mapped[dt.time]
    end_time: Mapped[dt.time]
    max_serials: Mapped[int] = mapped_column(server_default="40")
    avg_minutes_per_patient: Mapped[int] = mapped_column(server_default="7")
    current_serial: Mapped[int] = mapped_column(server_default="0")
    is_available: Mapped[bool] = mapped_column(server_default=true())

    doctor: Mapped["Doctor"] = relationship(back_populates="schedules")
    serials: Mapped[list["Serial"]] = relationship(back_populates="schedule")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(11), unique=True)
    created_at: Mapped[CreatedAt]

    serials: Mapped[list["Serial"]] = relationship(back_populates="patient")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role = 'super_admin' OR hospital_id IS NOT NULL",
            name="ck_users_super_admin_or_hospital",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(11), unique=True)
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole, "user_role"))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[CreatedAt]

    hospital: Mapped["Hospital | None"] = relationship(back_populates="users")
    created_serials: Mapped[list["Serial"]] = relationship(back_populates="creator")


class Serial(Base):
    __tablename__ = "serials"
    __table_args__ = (
        UniqueConstraint("schedule_id", "serial_no", name="uq_serials_schedule_serial_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("doctor_schedules.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    serial_no: Mapped[int]
    status: Mapped[SerialStatus] = mapped_column(
        enum_type(SerialStatus, "serial_status"),
        server_default=SerialStatus.WAITING.value,
    )
    source: Mapped[SerialSource] = mapped_column(
        enum_type(SerialSource, "serial_source"),
        server_default=SerialSource.APP.value,
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    schedule: Mapped["DoctorSchedule"] = relationship(back_populates="serials")
    patient: Mapped["Patient"] = relationship(back_populates="serials")
    creator: Mapped["User | None"] = relationship(back_populates="created_serials")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="serial")


class Notification(Base):
    """Mock SMS log: records messages instead of sending them."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_id: Mapped[int | None] = mapped_column(ForeignKey("serials.id"))
    phone: Mapped[str] = mapped_column(String(11))
    message: Mapped[str] = mapped_column(String(300))
    type: Mapped[NotificationType] = mapped_column(
        enum_type(NotificationType, "notification_type"),
    )
    status: Mapped[NotificationStatus] = mapped_column(
        enum_type(NotificationStatus, "notification_status"),
        server_default=NotificationStatus.SENT.value,
    )
    created_at: Mapped[CreatedAt]

    serial: Mapped["Serial | None"] = relationship(back_populates="notifications")
