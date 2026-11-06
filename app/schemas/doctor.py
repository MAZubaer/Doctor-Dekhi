"""Response schemas for doctors."""

import datetime as dt

from pydantic import BaseModel


class AvailableDoctorOut(BaseModel):
    """One bookable schedule. A doctor with two sessions appears twice."""

    doctor_id: int
    doctor_name: str
    specialty: str | None
    schedule_id: int
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    serials_booked: int
    serials_left: int
