"""Read operations for hospitals and departments."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Department, Hospital


def list_hospitals(db: Session) -> Sequence[Hospital]:
    return db.scalars(select(Hospital).order_by(Hospital.id)).all()


def list_departments(db: Session, hospital_id: int) -> Sequence[Department]:
    if db.get(Hospital, hospital_id) is None:
        raise NotFoundError(
            "HOSPITAL_NOT_FOUND",
            f"Hospital {hospital_id} was not found.",
        )
    return db.scalars(
        select(Department)
        .where(Department.hospital_id == hospital_id)
        .order_by(Department.name)
    ).all()
