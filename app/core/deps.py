"""Authentication dependencies and the hospital access checks for staff."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.security import decode_user_id
from app.database import DbSession
from app.models import Department, Doctor, DoctorSchedule, Serial, User, UserRole

# auto_error=False lets get_current_user return our own 401 error shape.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    if token is None:
        raise UnauthorizedError("NOT_AUTHENTICATED", "Log in to use this endpoint.")

    user = db.get(User, decode_user_id(token), options=[joinedload(User.hospital)])
    if user is None or not user.is_active:
        raise UnauthorizedError("INVALID_TOKEN", "The access token is invalid.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Build a dependency that only lets users with one of these roles through."""

    def check_role(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError(
                "FORBIDDEN_ROLE",
                "Your role does not have access to this endpoint.",
            )
        return user

    return check_role


StaffUser = Annotated[
    User,
    Depends(require_roles(UserRole.STAFF, UserRole.HOSPITAL_ADMIN, UserRole.SUPER_ADMIN)),
]
AdminUser = Annotated[
    User,
    Depends(require_roles(UserRole.HOSPITAL_ADMIN, UserRole.SUPER_ADMIN)),
]


def ensure_hospital_access(user: User, hospital_id: int) -> None:
    """Allow a super_admin everywhere and other staff only in their own hospital."""
    if user.role is not UserRole.SUPER_ADMIN and user.hospital_id != hospital_id:
        raise ForbiddenError(
            "HOSPITAL_ACCESS_DENIED",
            "You can only access your own hospital.",
        )


def get_schedule_for_staff(db: Session, schedule_id: int, user: User) -> DoctorSchedule:
    schedule = db.get(
        DoctorSchedule,
        schedule_id,
        options=[joinedload(DoctorSchedule.doctor).joinedload(Doctor.department)],
    )
    if schedule is None:
        raise NotFoundError("SCHEDULE_NOT_FOUND", f"Schedule {schedule_id} was not found.")
    ensure_hospital_access(user, schedule.doctor.department.hospital_id)
    return schedule


def get_serial_for_staff(db: Session, serial_id: int, user: User) -> Serial:
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
    ensure_hospital_access(user, serial.schedule.doctor.department.hospital_id)
    return serial
