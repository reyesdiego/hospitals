"""Bed search, reservations and cleaning endpoints."""

import uuid

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.api.presenters import bed_read
from app.schemas.domain import BedRead
from app.schemas.workflow import (
    BedOperationCreate,
    BedReservationCancelCreate,
    BedReservationCreate,
    BedReservationRead,
    BedStatusHistoryRead,
)
from app.services.bed_reservation import BedReservationService
from app.services.bed_status import BedStatusService

router = APIRouter(tags=["bed-workflow"])


@router.get("/beds/available", response_model=list[BedRead])
async def search_available_beds(
    session: DbSession,
    facility_id: uuid.UUID | None = None,
    ward: str | None = None,
    room_id: uuid.UUID | None = None,
):
    """Compatible beds for an admission: available, unreserved and unoccupied."""

    rows = await BedStatusService(session).search_available(
        facility_id=facility_id,
        ward=ward,
        room_id=room_id,
    )
    return [await bed_read(session, bed, room) for bed, room in rows]


@router.get("/beds/{bed_id}/status-history", response_model=list[BedStatusHistoryRead])
async def bed_status_history(bed_id: uuid.UUID, session: DbSession):
    return await BedStatusService(session).history(bed_id)


@router.post("/beds/{bed_id}/cleaning/start", response_model=BedRead)
async def start_bed_cleaning(
    bed_id: uuid.UUID,
    payload: BedOperationCreate,
    session: DbSession,
):
    bed = await BedStatusService(session).start_cleaning(
        bed_id,
        changed_by=payload.changed_by,
        reason=payload.reason,
    )
    return await bed_read(session, bed)


@router.post("/beds/{bed_id}/cleaning/complete", response_model=BedRead)
async def complete_bed_cleaning(
    bed_id: uuid.UUID,
    payload: BedOperationCreate,
    session: DbSession,
):
    bed = await BedStatusService(session).complete_cleaning(
        bed_id,
        changed_by=payload.changed_by,
        reason=payload.reason,
    )
    return await bed_read(session, bed)


@router.get(
    "/hospitalizations/{hospitalization_id}/bed-reservations",
    response_model=list[BedReservationRead],
)
async def list_bed_reservations(hospitalization_id: uuid.UUID, session: DbSession):
    return await BedReservationService(session).list_for_hospitalization(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/bed-reservations",
    response_model=BedReservationRead,
    status_code=201,
)
async def reserve_bed(
    hospitalization_id: uuid.UUID,
    payload: BedReservationCreate,
    session: DbSession,
):
    """Hold an available bed. The reservation expires so abandoned flows free the bed."""

    return await BedReservationService(session).reserve(
        hospitalization_id,
        payload.bed_id,
        expires_in_minutes=payload.expires_in_minutes,
        reserved_by=payload.reserved_by,
        reason=payload.reason,
    )


@router.post("/bed-reservations/{reservation_id}/cancel", response_model=BedReservationRead)
async def cancel_bed_reservation(
    reservation_id: uuid.UUID,
    payload: BedReservationCancelCreate,
    session: DbSession,
):
    return await BedReservationService(session).cancel(
        reservation_id,
        cancelled_by=payload.cancelled_by,
        reason=payload.reason,
    )


@router.post("/bed-reservations/expire-due", response_model=list[BedReservationRead])
async def expire_due_bed_reservations(session: DbSession):
    """Release beds whose reservation expired; intended for a scheduled job."""

    return await BedReservationService(session).expire_due()
