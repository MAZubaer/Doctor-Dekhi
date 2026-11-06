"""Patient routes for finding available doctors."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.database import DbSession
from app.schemas.common import MAX_DB_ID, VALIDATION_RESPONSE, error_response
from app.schemas.doctor import AvailableDoctorOut
from app.services import doctor_service
from app.services.demo_service import keep_demo_data_current

router = APIRouter(
    prefix="/doctors",
    tags=["Patient"],
    dependencies=[Depends(keep_demo_data_current)],
)


@router.get(
    "/available",
    summary="List available doctors",
    description=(
        "Returns the schedules that can still be booked in a department on a date. "
        "Each row has the `schedule_id` needed for booking.\n\n"
        "Inactive doctors, unavailable schedules and today's sessions that have "
        "already ended are left out. Full schedules stay in the list with "
        "`serials_left` set to 0."
    ),
    responses={
        400: error_response(
            "The date is in the past",
            ("DATE_IN_PAST", "Date cannot be in the past."),
        ),
        404: error_response(
            "The department does not exist",
            ("DEPARTMENT_NOT_FOUND", "Department 99 was not found."),
        ),
        422: VALIDATION_RESPONSE,
    },
)
def list_available_doctors(
    department_id: Annotated[int, Query(gt=0, le=MAX_DB_ID)],
    db: DbSession,
    date: Annotated[
        dt.date | None,
        Query(description="YYYY-MM-DD. Defaults to today in Bangladesh time."),
    ] = None,
) -> list[AvailableDoctorOut]:
    return doctor_service.list_available(db, department_id, date)
