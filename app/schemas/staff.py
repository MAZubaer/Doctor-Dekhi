"""Request and response schemas for the staff queue endpoints."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models import SerialSource, SerialStatus
from app.schemas.common import MAX_DB_ID
from app.schemas.serial import SerialOut

# Named examples, so Swagger's prefilled request is the plain call that always works.
CALL_NEXT_EXAMPLES = {
    "plain": {
        "summary": "Call the next patient",
        "value": {},
    },
    "guarded": {
        "summary": "With the double-click guard",
        "description": "Returns 409 QUEUE_CHANGED unless the current serial is still 4.",
        "value": {"expected_current_serial": 4},
    },
}


class QueueCounts(BaseModel):
    waiting: int
    serving: int
    done: int
    missed: int


class ScheduleSummaryOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schedule_id": 2,
                    "doctor_name": "Dr. Mahmudul Hasan",
                    "department_name": "Medicine",
                    "hospital_name": "Dhaka Medical College Hospital",
                    "date": "2026-11-08",
                    "start_time": "16:00:00",
                    "end_time": "23:30:00",
                    "is_available": True,
                    "max_serials": 30,
                    "current_serial": 4,
                    "counts": {"waiting": 4, "serving": 1, "done": 2, "missed": 1},
                }
            ]
        }
    )

    schedule_id: int
    doctor_name: str
    department_name: str
    hospital_name: str
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    is_available: bool
    max_serials: int
    current_serial: int
    counts: QueueCounts


class QueueEntryOut(BaseModel):
    """One serial in a staff queue view. The phone is shown in full for calling."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 4,
                    "serial_no": 4,
                    "status": "serving",
                    "source": "walk_in",
                    "patient_name": "Shirin Akter",
                    "phone": "01900000004",
                    "created_by": 3,
                    "created_at": "2026-11-08T09:40:00+06:00",
                },
                {
                    "id": 5,
                    "serial_no": 5,
                    "status": "waiting",
                    "source": "app",
                    "patient_name": "Mizanur Rahman",
                    "phone": "01900000005",
                    "created_by": None,
                    "created_at": "2026-11-08T09:45:00+06:00",
                },
            ]
        }
    )

    id: int
    serial_no: int
    status: SerialStatus
    source: SerialSource
    patient_name: str
    phone: str
    created_by: int | None
    created_at: dt.datetime


class CallNextRequest(BaseModel):
    expected_current_serial: int | None = Field(
        default=None,
        ge=0,
        le=MAX_DB_ID,
        description="The current serial on the caller's screen. Leave out to skip the check.",
    )


class CallNextOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": "Now serving serial #5.",
                    "finished_serial": {
                        "id": 4,
                        "serial_no": 4,
                        "status": "done",
                        "source": "walk_in",
                        "patient_name": "Shirin Akter",
                        "phone": "019****0004",
                        "schedule_id": 2,
                        "doctor_name": "Dr. Mahmudul Hasan",
                        "schedule_date": "2026-11-08",
                        "start_time": "16:00:00",
                        "created_at": "2026-11-08T09:40:00+06:00",
                    },
                    "serving_serial": {
                        "id": 5,
                        "serial_no": 5,
                        "status": "serving",
                        "source": "app",
                        "patient_name": "Mizanur Rahman",
                        "phone": "019****0005",
                        "schedule_id": 2,
                        "doctor_name": "Dr. Mahmudul Hasan",
                        "schedule_date": "2026-11-08",
                        "start_time": "16:00:00",
                        "created_at": "2026-11-08T09:45:00+06:00",
                    },
                    "current_serial": 5,
                    "counts": {"waiting": 3, "serving": 1, "done": 3, "missed": 1},
                }
            ]
        }
    )

    message: str
    finished_serial: SerialOut | None
    serving_serial: SerialOut | None
    current_serial: int
    counts: QueueCounts


class AvailabilityUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"is_available": False}]})

    is_available: bool


class AvailabilityOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"schedule_id": 2, "is_available": False, "patients_notified": 4}]
        }
    )

    schedule_id: int
    is_available: bool
    patients_notified: int = Field(
        description="Waiting patients who were sent a cancellation message."
    )
