"""Patient routes for browsing hospitals and departments."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path

from app.database import DbSession
from app.models import Department, Hospital
from app.schemas.common import MAX_DB_ID, VALIDATION_RESPONSE, error_response
from app.schemas.hospital import DepartmentOut, HospitalOut
from app.services import hospital_service

router = APIRouter(prefix="/hospitals", tags=["Patient"])


@router.get(
    "",
    response_model=list[HospitalOut],
    summary="List hospitals",
    description="Returns every hospital. Use an `id` from here to list its departments.",
)
def list_hospitals(db: DbSession) -> Sequence[Hospital]:
    return hospital_service.list_hospitals(db)


@router.get(
    "/{hospital_id}/departments",
    response_model=list[DepartmentOut],
    summary="List a hospital's departments",
    description="Returns the departments of one hospital, sorted by name.",
    responses={
        404: error_response(
            "The hospital does not exist",
            ("HOSPITAL_NOT_FOUND", "Hospital 99 was not found."),
        ),
        422: VALIDATION_RESPONSE,
    },
)
def list_departments(
    hospital_id: Annotated[int, Path(gt=0, le=MAX_DB_ID)],
    db: DbSession,
) -> Sequence[Department]:
    return hospital_service.list_departments(db, hospital_id)
