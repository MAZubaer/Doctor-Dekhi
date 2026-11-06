"""Response schemas for hospitals and departments."""

from pydantic import BaseModel, ConfigDict


class HospitalOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "name": "Dhaka Medical College Hospital",
                    "address": "Secretariat Road, Bakshibazar, Dhaka 1000",
                    "district": "Dhaka",
                }
            ]
        },
    )

    id: int
    name: str
    address: str | None
    district: str


class DepartmentOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": [{"id": 1, "hospital_id": 1, "name": "Medicine"}]},
    )

    id: int
    hospital_id: int
    name: str
