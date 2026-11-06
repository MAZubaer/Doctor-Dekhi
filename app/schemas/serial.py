"""Request and response schemas for serials and queue status."""

import datetime as dt
import re
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.phone import mask_phone, normalize_phone
from app.models import Serial, SerialSource, SerialStatus
from app.schemas.common import MAX_DB_ID

# English and Bangla letters, spaces and dots. The Bangla range leaves out
# Bangla digits and currency signs.
NAME_PATTERN = re.compile(r"[A-Za-zঀ-৥ৰৱ .]+")


class SerialCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schedule_id": 1,
                    "patient_name": "Md. Rahim Uddin",
                    "phone": "+8801712345678",
                }
            ]
        }
    )

    schedule_id: int = Field(gt=0, le=MAX_DB_ID)
    patient_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)
    ]
    phone: str = Field(
        description="01XXXXXXXXX, +8801XXXXXXXXX or 8801XXXXXXXXX. Spaces and dashes are allowed."
    )

    @field_validator("patient_name")
    @classmethod
    def check_patient_name(cls, value: str) -> str:
        has_letter = any(character.isalpha() for character in value)
        if not has_letter or not NAME_PATTERN.fullmatch(value):
            raise ValueError("Name can only contain letters, spaces and dots.")
        return value

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)


class SerialOut(BaseModel):
    id: int
    serial_no: int
    status: SerialStatus
    source: SerialSource
    patient_name: str
    phone: str = Field(description="Masked, for example 017****5678")
    schedule_id: int
    doctor_name: str
    schedule_date: dt.date
    start_time: dt.time
    created_at: dt.datetime

    @classmethod
    def from_serial(cls, serial: Serial) -> Self:
        schedule = serial.schedule
        return cls(
            id=serial.id,
            serial_no=serial.serial_no,
            status=serial.status,
            source=serial.source,
            patient_name=serial.patient.name,
            phone=mask_phone(serial.patient.phone),
            schedule_id=schedule.id,
            doctor_name=schedule.doctor.name,
            schedule_date=schedule.date,
            start_time=schedule.start_time,
            created_at=serial.created_at,
        )


class QueueStatusOut(BaseModel):
    serial_id: int
    serial_no: int
    status: SerialStatus
    now_serving: int = Field(description="The serial being seen now. 0 means not started.")
    people_ahead: int
    estimated_wait_minutes: int
    message: str
    doctor_name: str
    department_name: str
    hospital_name: str
    schedule_date: dt.date
    start_time: dt.time
    end_time: dt.time
