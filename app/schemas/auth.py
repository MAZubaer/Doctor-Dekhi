"""Response schemas for login and the current user."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict

from app.models import User, UserRole


class UserSummary(BaseModel):
    name: str
    role: UserRole
    hospital_name: str | None

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            name=user.name,
            role=user.role,
            hospital_name=user.hospital.name if user.hospital else None,
        )


class LoginResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "user": {
                        "name": "Imran Hossain",
                        "role": "staff",
                        "hospital_name": "Dhaka Medical College Hospital",
                    },
                }
            ]
        }
    )

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary


class UserProfile(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 3,
                    "name": "Imran Hossain",
                    "phone": "01700000012",
                    "role": "staff",
                    "hospital_id": 1,
                    "hospital_name": "Dhaka Medical College Hospital",
                    "is_active": True,
                    "created_at": "2026-11-08T08:00:00+06:00",
                }
            ]
        }
    )

    id: int
    name: str
    phone: str
    role: UserRole
    hospital_id: int | None
    hospital_name: str | None
    is_active: bool
    created_at: dt.datetime

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            name=user.name,
            phone=user.phone,
            role=user.role,
            hospital_id=user.hospital_id,
            hospital_name=user.hospital.name if user.hospital else None,
            is_active=user.is_active,
            created_at=user.created_at,
        )
