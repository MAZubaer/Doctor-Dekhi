"""Staff routes for running a hospital's queues."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, status

from app.core.deps import AdminUser, StaffUser, get_schedule_for_staff, get_serial_for_staff
from app.database import DbSession
from app.schemas.common import (
    MAX_DB_ID,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_RESPONSE,
    error_response,
)
from app.schemas.serial import SerialOut, WalkInCreate
from app.schemas.staff import (
    CALL_NEXT_EXAMPLES,
    AvailabilityOut,
    AvailabilityUpdate,
    CallNextOut,
    CallNextRequest,
    QueueEntryOut,
    ScheduleSummaryOut,
)
from app.services import queue_service
from app.services.demo_service import keep_demo_data_current

HOSPITAL_ACCESS_DENIED = ("HOSPITAL_ACCESS_DENIED", "You can only access your own hospital.")

router = APIRouter(
    prefix="/staff",
    tags=["Staff"],
    dependencies=[Depends(keep_demo_data_current)],
    responses={
        401: UNAUTHORIZED_RESPONSE,
        403: error_response("The user may not access this hospital", HOSPITAL_ACCESS_DENIED),
        422: VALIDATION_RESPONSE,
    },
)

ScheduleId = Annotated[int, Path(gt=0, le=MAX_DB_ID)]
SerialId = Annotated[int, Path(gt=0, le=MAX_DB_ID)]

SCHEDULE_NOT_FOUND = error_response(
    "The schedule does not exist",
    ("SCHEDULE_NOT_FOUND", "Schedule 99 was not found."),
)


@router.get(
    "/schedules",
    summary="List schedules",
    description=(
        "Lists schedules on a date with their queue counts and current serial.\n\n"
        "Staff and hospital admins see their own hospital. A super admin sees every "
        "hospital, and can narrow the list with `hospital_id`."
    ),
    responses={
        404: error_response(
            "The hospital does not exist",
            ("HOSPITAL_NOT_FOUND", "Hospital 99 was not found."),
        ),
    },
)
def list_schedules(
    db: DbSession,
    user: StaffUser,
    date: Annotated[
        dt.date | None,
        Query(description="YYYY-MM-DD. Defaults to today in Bangladesh time."),
    ] = None,
    hospital_id: Annotated[
        int | None,
        Query(gt=0, le=MAX_DB_ID, description="Super admin only filter."),
    ] = None,
) -> list[ScheduleSummaryOut]:
    return queue_service.list_schedules(db, user, date, hospital_id)


@router.get(
    "/schedules/{schedule_id}/queue",
    summary="List a schedule's queue",
    description=(
        "Lists every serial in order. Phone numbers are shown in full here so staff "
        "can call patients."
    ),
    responses={404: SCHEDULE_NOT_FOUND},
)
def get_queue(
    schedule_id: ScheduleId,
    db: DbSession,
    user: StaffUser,
) -> list[QueueEntryOut]:
    schedule = get_schedule_for_staff(db, schedule_id, user)
    return queue_service.get_queue(db, schedule)


@router.post(
    "/schedules/{schedule_id}/next",
    summary="Call the next patient",
    description=(
        "Marks the patient being served as done and moves the lowest waiting serial "
        "up to serving. Works only on today's available schedules.\n\n"
        "Sends a mock `turn_near` SMS to every waiting patient 3 or fewer places from "
        "being served who has not had one yet. When nobody is left waiting, it finishes "
        "the current patient and reports that the queue is finished.\n\n"
        "The body is optional. Send `expected_current_serial` to guard against a double "
        "click: if the queue has already moved, the call returns 409 `QUEUE_CHANGED` "
        "and changes nothing."
    ),
    responses={
        400: error_response(
            "The queue cannot move",
            ("SCHEDULE_NOT_ACTIVE", "Patients can only be called on an available schedule for today."),
            ("QUEUE_EMPTY", "There are no patients in this queue."),
        ),
        404: SCHEDULE_NOT_FOUND,
        409: error_response(
            "The queue moved before this call arrived",
            (
                "QUEUE_CHANGED",
                "The queue has moved on. The current serial is #5.",
                {"expected_current_serial": 4, "current_serial": 5},
            ),
        ),
    },
)
def call_next(
    schedule_id: ScheduleId,
    db: DbSession,
    user: StaffUser,
    data: Annotated[CallNextRequest | None, Body(openapi_examples=CALL_NEXT_EXAMPLES)] = None,
) -> CallNextOut:
    schedule = get_schedule_for_staff(db, schedule_id, user)
    expected_current_serial = data.expected_current_serial if data else None
    return queue_service.call_next(db, schedule, user, expected_current_serial)


@router.post(
    "/serials/{serial_id}/missed",
    summary="Mark a patient as missed",
    description=(
        "Marks a waiting or serving patient as missed. Missed patients are skipped "
        "by the queue and do not count towards anyone's wait."
    ),
    responses={
        400: error_response(
            "The serial cannot be marked as missed",
            (
                "INVALID_STATUS_TRANSITION",
                "A serial that is done cannot become missed.",
                {"from": "done", "to": "missed"},
            ),
        ),
        404: error_response(
            "The serial does not exist",
            ("SERIAL_NOT_FOUND", "Serial 99 was not found."),
        ),
    },
)
def mark_missed(
    serial_id: SerialId,
    db: DbSession,
    user: StaffUser,
) -> SerialOut:
    serial = get_serial_for_staff(db, serial_id, user)
    return SerialOut.from_serial(queue_service.mark_missed(db, serial, user))


@router.post(
    "/schedules/{schedule_id}/walk-in",
    status_code=status.HTTP_201_CREATED,
    summary="Add a walk-in patient",
    description=(
        "Books the next serial for a patient at the counter, with the same rules as "
        "an app booking. The serial records `walk_in` as its source and the staff "
        "member who created it."
    ),
    responses={
        400: error_response(
            "The schedule cannot be booked",
            ("DOCTOR_UNAVAILABLE", "This doctor is not available for this schedule."),
            ("SCHEDULE_CLOSED", "This schedule has ended and can no longer be booked."),
        ),
        404: SCHEDULE_NOT_FOUND,
        409: error_response(
            "The booking conflicts with existing serials",
            (
                "ALREADY_BOOKED",
                "This patient already has serial #5 on this schedule.",
                {"serial_id": 5, "serial_no": 5},
            ),
            ("SCHEDULE_FULL", "No serials left for this doctor on this schedule."),
            (
                "BOOKING_CONFLICT",
                "Too many people are booking this schedule right now. Please try again.",
            ),
        ),
    },
)
def add_walk_in(
    schedule_id: ScheduleId,
    data: WalkInCreate,
    db: DbSession,
    user: StaffUser,
) -> SerialOut:
    schedule = get_schedule_for_staff(db, schedule_id, user)
    return SerialOut.from_serial(queue_service.add_walk_in(db, schedule, data, user))


@router.patch(
    "/schedules/{schedule_id}/availability",
    summary="Open or cancel a schedule",
    description=(
        "Hospital admins and super admins only. Sets whether a schedule can be booked "
        "and called.\n\n"
        "Setting it to false sends a mock `cancelled` SMS to every waiting patient. "
        "Their serials stay waiting and show as on hold, so the queue can continue if "
        "the schedule is reopened."
    ),
    responses={
        403: error_response(
            "The user may not change this schedule",
            ("FORBIDDEN_ROLE", "Your role does not have access to this endpoint."),
            HOSPITAL_ACCESS_DENIED,
        ),
        404: SCHEDULE_NOT_FOUND,
    },
)
def set_availability(
    schedule_id: ScheduleId,
    data: AvailabilityUpdate,
    db: DbSession,
    user: AdminUser,
) -> AvailabilityOut:
    schedule = get_schedule_for_staff(db, schedule_id, user)
    return queue_service.set_availability(db, schedule, data.is_available, user)
