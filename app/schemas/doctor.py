"""Response schemas for doctors."""

import datetime as dt

from pydantic import BaseModel, ConfigDict


class AvailableDoctorOut(BaseModel):
    """One bookable schedule. A doctor with two sessions appears twice."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "doctor_id": 1,
                    "doctor_name": "Dr. Mahmudul Hasan",
                    "specialty": "Internal Medicine",
                    "schedule_id": 2,
                    "date": "2026-11-08",
                    "start_time": "16:00:00",
                    "end_time": "23:30:00",
                    "serials_booked": 8,
                    "serials_left": 22,
                }
            ]
        }
    )

    doctor_id: int
    doctor_name: str
    specialty: str | None
    schedule_id: int
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    serials_booked: int
    serials_left: int
