"""Patient routes for booking a serial and checking the queue."""

from typing import Annotated

from fastapi import APIRouter, Path, status

from app.database import DbSession
from app.schemas.common import MAX_DB_ID, VALIDATION_RESPONSE, error_response
from app.schemas.serial import QueueStatusOut, SerialCreate, SerialOut
from app.services import queue_service, serial_service

router = APIRouter(prefix="/serials", tags=["Patient"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Book a serial",
    description=(
        "Books the next serial on a schedule and records a mock confirmation SMS. "
        "Get a `schedule_id` from `GET /doctors/available`.\n\n"
        "A new phone number creates a patient. A known phone number keeps the "
        "patient's existing name."
    ),
    responses={
        400: error_response(
            "The schedule cannot be booked",
            ("DOCTOR_UNAVAILABLE", "This doctor is not available for this schedule."),
            ("SCHEDULE_CLOSED", "This schedule has ended and can no longer be booked."),
        ),
        404: error_response(
            "The schedule does not exist",
            ("SCHEDULE_NOT_FOUND", "Schedule 99 was not found."),
        ),
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
        422: VALIDATION_RESPONSE,
    },
)
def book_serial(data: SerialCreate, db: DbSession) -> SerialOut:
    return SerialOut.from_serial(serial_service.book_serial(db, data))


@router.get(
    "/{serial_id}/status",
    summary="Check queue status",
    description=(
        "Shows who is being served, how many waiting patients are ahead and the "
        "estimated wait. Missed patients are not counted as ahead.\n\n"
        "If the schedule is made unavailable, a waiting patient sees `is_on_hold: true`, "
        "and `estimated_wait_minutes` is null until the schedule reopens."
    ),
    responses={
        404: error_response(
            "The serial does not exist",
            ("SERIAL_NOT_FOUND", "Serial 99 was not found."),
        ),
        422: VALIDATION_RESPONSE,
    },
)
def get_queue_status(
    serial_id: Annotated[int, Path(gt=0, le=MAX_DB_ID)],
    db: DbSession,
) -> QueueStatusOut:
    return queue_service.get_status(db, serial_id)
