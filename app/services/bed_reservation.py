"""Bed reservations: a hold on a bed that is not yet a physical occupancy."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, integrity_conflict
from app.models.audit import HospitalizationEventType
from app.models.bed import (
    Bed,
    BedAssignment,
    BedReservation,
    BedReservationStatus,
    BedStatus,
)
from app.models.hospitalization import OPEN_HOSPITALIZATION_STATUSES, Hospitalization
from app.services.audit import record_event
from app.services.bed_status import apply_bed_status


class BedReservationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def reserve(
        self,
        hospitalization_id: uuid.UUID,
        bed_id: uuid.UUID,
        *,
        expires_in_minutes: int | None = 120,
        reserved_by: str | None = None,
        reason: str | None = None,
    ) -> BedReservation:
        async with (
            integrity_conflict(self.session, "La cama ya tiene una reserva activa"),
            self.session.begin(),
        ):
            hospitalization = await self._hospitalization_for_update(hospitalization_id)
            if hospitalization.status not in OPEN_HOSPITALIZATION_STATUSES:
                raise DomainError("La internación no está activa", 409)

            # Locking the bed row first serializes concurrent reservations on it.
            bed = await self.session.get(Bed, bed_id, with_for_update=True)
            if not bed:
                raise DomainError("Cama inexistente", 404)

            now = datetime.now(UTC)
            await self._expire_reservation_for_bed(bed, now=now)

            if bed.status != BedStatus.AVAILABLE:
                raise DomainError("La cama no está disponible", 409)
            if await self._active_assignment_for_bed(bed_id):
                raise DomainError("La cama está ocupada por una internación", 409)
            if await self.active_for_hospitalization(hospitalization_id, lock=True):
                raise DomainError("La internación ya tiene una reserva activa", 409)
            if await self._active_assignment_for_hospitalization(hospitalization_id):
                raise DomainError("La internación ya tiene una cama asignada", 409)

            reservation = BedReservation(
                hospitalization_id=hospitalization_id,
                bed_id=bed_id,
                status=BedReservationStatus.ACTIVE,
                reserved_at=now,
                expires_at=now + timedelta(minutes=expires_in_minutes)
                if expires_in_minutes
                else None,
                reserved_by=reserved_by,
                reason=reason,
            )
            self.session.add(reservation)
            apply_bed_status(
                self.session,
                bed,
                BedStatus.RESERVED,
                changed_by=reserved_by,
                reason=reason,
                at=now,
                hospitalization_id=hospitalization_id,
                record_audit_event=False,
            )
            record_event(
                self.session,
                HospitalizationEventType.BED_RESERVED,
                hospitalization_id=hospitalization_id,
                bed_id=bed_id,
                patient_id=hospitalization.patient_id,
                actor=reserved_by,
                occurred_at=now,
                details={"expires_at": reservation.expires_at.isoformat() if reservation.expires_at else None},
            )
            await self.session.flush()
            return reservation

    async def cancel(
        self,
        reservation_id: uuid.UUID,
        *,
        cancelled_by: str | None = None,
        reason: str | None = None,
    ) -> BedReservation:
        async with self.session.begin():
            reservation = await self.session.get(
                BedReservation,
                reservation_id,
                with_for_update=True,
            )
            if not reservation:
                raise DomainError("Reserva inexistente", 404)
            if reservation.status != BedReservationStatus.ACTIVE:
                raise DomainError("La reserva no está activa", 409)

            now = datetime.now(UTC)
            await self._close_reservation(
                reservation,
                BedReservationStatus.CANCELLED,
                now=now,
                actor=cancelled_by,
                reason=reason,
                event_type=HospitalizationEventType.BED_RESERVATION_CANCELLED,
            )
            return reservation

    async def expire_due(self, *, now: datetime | None = None) -> list[BedReservation]:
        """Release beds held by reservations that were never confirmed."""

        moment = now or datetime.now(UTC)
        async with self.session.begin():
            expired = list(
                (
                    await self.session.scalars(
                        select(BedReservation)
                        .where(
                            BedReservation.status == BedReservationStatus.ACTIVE,
                            BedReservation.expires_at.is_not(None),
                            BedReservation.expires_at <= moment,
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for reservation in expired:
                await self._close_reservation(
                    reservation,
                    BedReservationStatus.EXPIRED,
                    now=moment,
                    actor=None,
                    reason="Reserva vencida",
                    event_type=HospitalizationEventType.BED_RESERVATION_EXPIRED,
                )
            return expired

    async def list_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
    ) -> list[BedReservation]:
        return list(
            (
                await self.session.scalars(
                    select(BedReservation)
                    .where(BedReservation.hospitalization_id == hospitalization_id)
                    .order_by(BedReservation.reserved_at.desc())
                )
            ).all()
        )

    async def active_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> BedReservation | None:
        stmt = select(BedReservation).where(
            BedReservation.hospitalization_id == hospitalization_id,
            BedReservation.status == BedReservationStatus.ACTIVE,
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def active_for_bed(
        self,
        bed_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> BedReservation | None:
        stmt = select(BedReservation).where(
            BedReservation.bed_id == bed_id,
            BedReservation.status == BedReservationStatus.ACTIVE,
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def _close_reservation(
        self,
        reservation: BedReservation,
        status: BedReservationStatus,
        *,
        now: datetime,
        actor: str | None,
        reason: str | None,
        event_type: HospitalizationEventType,
    ) -> None:
        reservation.status = status
        if status == BedReservationStatus.CANCELLED:
            reservation.cancelled_at = now
        bed = await self.session.get(Bed, reservation.bed_id, with_for_update=True)
        if bed and bed.status == BedStatus.RESERVED:
            apply_bed_status(
                self.session,
                bed,
                BedStatus.AVAILABLE,
                changed_by=actor,
                reason=reason,
                at=now,
                record_audit_event=False,
            )
        record_event(
            self.session,
            event_type,
            hospitalization_id=reservation.hospitalization_id,
            bed_id=reservation.bed_id,
            actor=actor,
            occurred_at=now,
            details={"reason": reason},
        )

    async def _expire_reservation_for_bed(self, bed: Bed, *, now: datetime) -> None:
        reservation = await self.active_for_bed(bed.id, lock=True)
        if not reservation or not reservation.expires_at or reservation.expires_at > now:
            return
        await self._close_reservation(
            reservation,
            BedReservationStatus.EXPIRED,
            now=now,
            actor=None,
            reason="Reserva vencida",
            event_type=HospitalizationEventType.BED_RESERVATION_EXPIRED,
        )
        await self.session.flush()

    async def _hospitalization_for_update(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(
            Hospitalization,
            hospitalization_id,
            with_for_update=True,
        )
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _active_assignment_for_bed(self, bed_id: uuid.UUID) -> uuid.UUID | None:
        return await self.session.scalar(
            select(BedAssignment.id).where(
                BedAssignment.bed_id == bed_id,
                BedAssignment.ended_at.is_(None),
            )
        )

    async def _active_assignment_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
    ) -> uuid.UUID | None:
        return await self.session.scalar(
            select(BedAssignment.id).where(
                BedAssignment.hospitalization_id == hospitalization_id,
                BedAssignment.ended_at.is_(None),
            )
        )
