"""Operational bed status: transitions, cleaning and history."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Row, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import DomainError
from app.models.audit import HospitalizationEventType
from app.models.bed import (
    OPERATIONAL_BED_STATUSES,
    Bed,
    BedAssignment,
    BedReservation,
    BedReservationStatus,
    BedStatus,
    BedStatusHistory,
)
from app.models.hospitalization import Hospitalization
from app.models.patient import Patient
from app.models.room import Room
from app.services.audit import record_event

#: Statuses a bed can be moved out of when it is neither reserved nor occupied.
CLEANING_START_STATUSES = {BedStatus.PENDING_CLEANING}
CLEANING_COMPLETE_STATUSES = {BedStatus.CLEANING, BedStatus.PENDING_CLEANING}

_STATUS_EVENTS = {
    BedStatus.CLEANING: HospitalizationEventType.BED_CLEANING_STARTED,
    BedStatus.AVAILABLE: HospitalizationEventType.BED_AVAILABLE,
}


def apply_bed_status(
    session: AsyncSession,
    bed: Bed,
    new_status: BedStatus,
    *,
    changed_by: str | None = None,
    reason: str | None = None,
    at: datetime | None = None,
    hospitalization_id: uuid.UUID | None = None,
    record_audit_event: bool = True,
) -> BedStatusHistory:
    """Move a bed to ``new_status`` and append the change to ``bed_status_history``.

    Does not open a transaction: the caller owns the transaction boundary.
    """

    changed_at = at or datetime.now(UTC)
    history = BedStatusHistory(
        bed_id=bed.id,
        previous_status=bed.status,
        new_status=new_status,
        changed_at=changed_at,
        changed_by=changed_by,
        reason=reason,
    )
    bed.status = new_status
    session.add(history)
    if record_audit_event:
        record_event(
            session,
            _STATUS_EVENTS.get(new_status, HospitalizationEventType.BED_STATUS_CHANGED),
            bed_id=bed.id,
            hospitalization_id=hospitalization_id,
            actor=changed_by,
            occurred_at=changed_at,
            details={
                "previous_status": history.previous_status.value if history.previous_status else None,
                "new_status": new_status.value,
                "reason": reason,
            },
        )
    return history


class BedStatusService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_status(
        self,
        bed_id: uuid.UUID,
        status: BedStatus,
        *,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> Bed:
        if status not in OPERATIONAL_BED_STATUSES:
            raise DomainError(
                "La ocupación y la reserva se gestionan desde la internación",
                409,
            )

        async with self.session.begin():
            bed = await self._bed_for_update(bed_id)
            await self._require_free_bed(bed)
            if bed.status == status:
                return bed
            apply_bed_status(
                self.session,
                bed,
                status,
                changed_by=changed_by,
                reason=reason,
            )
            return bed

    async def start_cleaning(
        self,
        bed_id: uuid.UUID,
        *,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> Bed:
        async with self.session.begin():
            bed = await self._bed_for_update(bed_id)
            if bed.status not in CLEANING_START_STATUSES:
                raise DomainError("La cama no está pendiente de limpieza", 409)
            apply_bed_status(
                self.session,
                bed,
                BedStatus.CLEANING,
                changed_by=changed_by,
                reason=reason,
            )
            return bed

    async def complete_cleaning(
        self,
        bed_id: uuid.UUID,
        *,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> Bed:
        async with self.session.begin():
            bed = await self._bed_for_update(bed_id)
            if bed.status not in CLEANING_COMPLETE_STATUSES:
                raise DomainError("La cama no está en proceso de limpieza", 409)
            await self._require_free_bed(bed)
            apply_bed_status(
                self.session,
                bed,
                BedStatus.AVAILABLE,
                changed_by=changed_by,
                reason=reason,
            )
            return bed

    async def history(self, bed_id: uuid.UUID) -> list[BedStatusHistory]:
        await self._require_bed(bed_id)
        return list(
            (
                await self.session.scalars(
                    select(BedStatusHistory)
                    .where(BedStatusHistory.bed_id == bed_id)
                    .order_by(BedStatusHistory.changed_at.desc())
                )
            ).all()
        )

    async def board(self) -> Sequence[Row]:
        """Beds with their room, the patient occupying them and the reservation holder."""

        reservations = (
            select(
                BedReservation.bed_id,
                BedReservation.hospitalization_id,
                BedReservation.expires_at,
            )
            .where(BedReservation.status == BedReservationStatus.ACTIVE)
            .subquery()
        )
        assignments = (
            select(BedAssignment.bed_id, BedAssignment.hospitalization_id)
            .where(BedAssignment.ended_at.is_(None))
            .subquery()
        )
        occupying_stay = aliased(Hospitalization)
        reserving_stay = aliased(Hospitalization)
        occupant = aliased(Patient)
        holder = aliased(Patient)

        stmt = (
            select(Bed, Room, occupant, holder, reservations.c.expires_at)
            .join(Room, Room.id == Bed.room_id)
            .outerjoin(assignments, assignments.c.bed_id == Bed.id)
            .outerjoin(occupying_stay, occupying_stay.id == assignments.c.hospitalization_id)
            .outerjoin(occupant, occupant.id == occupying_stay.patient_id)
            .outerjoin(reservations, reservations.c.bed_id == Bed.id)
            .outerjoin(reserving_stay, reserving_stay.id == reservations.c.hospitalization_id)
            .outerjoin(holder, holder.id == reserving_stay.patient_id)
            .order_by(Room.ward, Room.code, Bed.code)
        )
        return (await self.session.execute(stmt)).all()

    async def search_available(
        self,
        *,
        facility_id: uuid.UUID | None = None,
        ward: str | None = None,
        room_id: uuid.UUID | None = None,
    ) -> Sequence[tuple[Bed, Room]]:
        """Compatible available beds. Criteria are limited to what the model supports:
        facility, ward and room."""

        stmt: Select = (
            select(Bed, Room)
            .join(Room, Room.id == Bed.room_id)
            .where(Bed.status == BedStatus.AVAILABLE)
            .where(
                ~select(BedAssignment.id)
                .where(
                    BedAssignment.bed_id == Bed.id,
                    BedAssignment.ended_at.is_(None),
                )
                .exists()
            )
            .where(
                ~select(BedReservation.id)
                .where(
                    BedReservation.bed_id == Bed.id,
                    BedReservation.status == BedReservationStatus.ACTIVE,
                )
                .exists()
            )
            .order_by(Room.ward, Room.code, Bed.code)
        )
        if facility_id:
            stmt = stmt.where(Bed.facility_id == facility_id)
        if ward:
            stmt = stmt.where(Room.ward == ward)
        if room_id:
            stmt = stmt.where(Bed.room_id == room_id)
        return (await self.session.execute(stmt)).all()

    async def _require_bed(self, bed_id: uuid.UUID) -> Bed:
        bed = await self.session.get(Bed, bed_id)
        if not bed:
            raise DomainError("Cama inexistente", 404)
        return bed

    async def _bed_for_update(self, bed_id: uuid.UUID) -> Bed:
        bed = await self.session.get(Bed, bed_id, with_for_update=True)
        if not bed:
            raise DomainError("Cama inexistente", 404)
        return bed

    async def _require_free_bed(self, bed: Bed) -> None:
        occupied = await self.session.scalar(
            select(BedAssignment.id).where(
                BedAssignment.bed_id == bed.id,
                BedAssignment.ended_at.is_(None),
            )
        )
        if occupied:
            raise DomainError("La cama está ocupada por una internación", 409)
        reserved = await self.session.scalar(
            select(BedReservation.id).where(
                BedReservation.bed_id == bed.id,
                BedReservation.status == BedReservationStatus.ACTIVE,
            )
        )
        if reserved:
            raise DomainError("La cama tiene una reserva activa", 409)
