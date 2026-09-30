"""Physical bed occupancy: confirmation of admission, transfers and release."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, integrity_conflict
from app.models.admission import Admission, AdmissionStatus, Episode
from app.models.audit import HospitalizationEventType
from app.models.bed import (
    Bed,
    BedAssignment,
    BedReservation,
    BedReservationStatus,
    BedStatus,
    BedTransfer,
    TransferStatus,
)
from app.models.hospitalization import (
    OPEN_HOSPITALIZATION_STATUSES,
    Hospitalization,
    HospitalizationStatus,
)
from app.schemas.domain import AdmissionArrivalCreate
from app.services.admission_arrival import record_arrival
from app.services.audit import record_event
from app.services.bed_status import apply_bed_status
from app.services.service_assignment import reassign_service

ACTIVE_HOSPITALIZATION_STATUSES = OPEN_HOSPITALIZATION_STATUSES
ASSIGNABLE_BED_STATUS = BedStatus.AVAILABLE


async def move_to_bed_facility(
    session: AsyncSession,
    hospitalization: Hospitalization,
    bed: Bed,
) -> None:
    """La internación queda en el centro de la cama que toma el paciente.

    Antes de ocupar la primera cama se elige entre las libres de todos los centros: si la
    que se reserva o se ocupa es de otro, la internación y su episodio pasan a ese centro.
    Los traslados no pasan por acá: mover de centro a alguien ya internado es una derivación.
    """

    if hospitalization.facility_id == bed.facility_id:
        return
    hospitalization.facility_id = bed.facility_id
    if hospitalization.episode_id:
        episode = await session.get(Episode, hospitalization.episode_id)
        if episode:
            episode.facility_id = bed.facility_id


class BedAssignmentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def assign(
        self,
        hospitalization_id: uuid.UUID,
        bed_id: uuid.UUID,
        commit: bool = True,
        assignment_reason: str | None = None,
        assigned_by: str | None = None,
        arrival: AdmissionArrivalCreate | None = None,
    ) -> BedAssignment:
        """Confirm the physical admission of the patient on a bed.

        Completes the reservation if the bed was held for this hospitalization, records the
        contact and consents taken on arrival, moves the bed to OCCUPIED and starts the
        hospitalization. Atomic when ``commit`` is true; otherwise it joins the transaction
        owned by the caller.
        """

        if not commit:
            return await self._assign_locked(
                hospitalization_id,
                bed_id,
                assignment_reason=assignment_reason,
                assigned_by=assigned_by,
                arrival=arrival,
            )

        async with integrity_conflict(
            self.session,
            "La cama o la internación ya tienen una asignación activa",
        ), self.session.begin():
            return await self._assign_locked(
                hospitalization_id,
                bed_id,
                assignment_reason=assignment_reason,
                assigned_by=assigned_by,
                arrival=arrival,
            )

    async def transfer(
        self,
        hospitalization_id: uuid.UUID,
        destination_bed_id: uuid.UUID,
        reason: str | None = None,
        requested_by: str | None = None,
        completed_by: str | None = None,
        service_id: uuid.UUID | None = None,
    ) -> BedTransfer:
        """Move a patient to another bed atomically: the patient never loses the origin
        bed unless the destination has been secured in the same transaction."""

        async with (
            integrity_conflict(self.session, "La cama destino dejó de estar disponible"),
            self.session.begin(),
        ):
            hospitalization = await self._hospitalization_for_update(hospitalization_id)
            self._validate_hospitalization_active(hospitalization)

            current_assignment = await self._active_assignment_for_hospitalization(
                hospitalization_id,
                lock=True,
            )
            if not current_assignment:
                raise DomainError("La internación no tiene una cama activa", 404)
            if current_assignment.bed_id == destination_bed_id:
                raise DomainError("La transferencia no puede apuntar a la misma cama", 409)

            beds = await self._lock_beds(current_assignment.bed_id, destination_bed_id)
            source_bed = beds.get(current_assignment.bed_id)
            destination_bed = beds.get(destination_bed_id)
            if not destination_bed:
                raise DomainError("Cama destino inexistente", 404)
            if not source_bed:
                raise DomainError("La cama actual de la internación no existe", 409)

            now = datetime.now(UTC)
            reservation = await self._reservation_to_complete(
                destination_bed,
                hospitalization_id,
            )
            if destination_bed.status != ASSIGNABLE_BED_STATUS and reservation is None:
                raise DomainError("La cama destino no está disponible", 409)
            if await self._active_assignment_for_bed(destination_bed_id, lock=True):
                raise DomainError("La cama destino no está disponible", 409)
            if reservation is not None:
                self._complete_reservation(reservation, now)

            transfer = BedTransfer(
                hospitalization_id=hospitalization_id,
                from_bed_id=source_bed.id,
                to_bed_id=destination_bed.id,
                status=TransferStatus.COMPLETED,
                requested_at=now,
                completed_at=now,
                reason=reason,
                requested_by=requested_by,
                completed_by=completed_by,
            )
            current_assignment.ended_at = now
            current_assignment.ended_by = completed_by
            apply_bed_status(
                self.session,
                source_bed,
                BedStatus.PENDING_CLEANING,
                changed_by=completed_by,
                reason=reason,
                at=now,
                hospitalization_id=hospitalization_id,
                record_audit_event=False,
            )

            new_assignment = BedAssignment(
                hospitalization_id=hospitalization_id,
                bed_id=destination_bed.id,
                started_at=now,
                assignment_reason=reason,
                assigned_by=completed_by,
            )
            apply_bed_status(
                self.session,
                destination_bed,
                BedStatus.OCCUPIED,
                changed_by=completed_by,
                reason=reason,
                at=now,
                hospitalization_id=hospitalization_id,
                record_audit_event=False,
            )
            self.session.add_all([transfer, new_assignment])
            record_event(
                self.session,
                HospitalizationEventType.PATIENT_TRANSFERRED,
                hospitalization_id=hospitalization_id,
                bed_id=destination_bed.id,
                patient_id=hospitalization.patient_id,
                actor=completed_by,
                occurred_at=now,
                details={
                    "from_bed_id": str(source_bed.id),
                    "to_bed_id": str(destination_bed.id),
                    "reason": reason,
                },
            )
            if service_id is not None:
                await reassign_service(
                    self.session,
                    hospitalization,
                    service_id,
                    at=now,
                    reason=reason,
                    assigned_by=completed_by,
                )
            await self.session.flush()
            return transfer

    async def end_active_assignment(
        self,
        hospitalization: Hospitalization,
        *,
        at: datetime,
        released_by: str | None = None,
        reason: str | None = None,
    ) -> BedAssignment:
        """End the current occupancy and send the bed to cleaning.

        Non-transactional: used by the physical-departure use case, which owns the
        transaction and the hospitalization lifecycle changes.
        """

        assignment = await self._active_assignment_for_hospitalization(
            hospitalization.id,
            lock=True,
        )
        if not assignment:
            raise DomainError("La internación no tiene una cama activa", 404)
        bed = await self.session.get(Bed, assignment.bed_id, with_for_update=True)
        if not bed:
            raise DomainError("Cama inexistente", 404)

        assignment.ended_at = at
        assignment.ended_by = released_by
        apply_bed_status(
            self.session,
            bed,
            BedStatus.PENDING_CLEANING,
            changed_by=released_by,
            reason=reason,
            at=at,
            hospitalization_id=hospitalization.id,
            record_audit_event=False,
        )
        record_event(
            self.session,
            HospitalizationEventType.BED_RELEASED,
            hospitalization_id=hospitalization.id,
            bed_id=bed.id,
            patient_id=hospitalization.patient_id,
            actor=released_by,
            occurred_at=at,
            details={"reason": reason},
        )
        return assignment

    async def list_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
    ) -> list[BedAssignment]:
        return list(
            (
                await self.session.scalars(
                    select(BedAssignment)
                    .where(BedAssignment.hospitalization_id == hospitalization_id)
                    .order_by(BedAssignment.started_at.desc())
                )
            ).all()
        )

    async def _assign_locked(
        self,
        hospitalization_id: uuid.UUID,
        bed_id: uuid.UUID,
        assignment_reason: str | None = None,
        assigned_by: str | None = None,
        arrival: AdmissionArrivalCreate | None = None,
    ) -> BedAssignment:
        hospitalization = await self._hospitalization_for_update(hospitalization_id)
        self._validate_hospitalization_active(hospitalization)

        bed = await self.session.get(Bed, bed_id, with_for_update=True)
        if not bed:
            raise DomainError("Cama inexistente", 404)

        now = datetime.now(UTC)
        reservation = await self._reservation_to_complete(bed, hospitalization_id)
        if bed.status != ASSIGNABLE_BED_STATUS and reservation is None:
            raise DomainError("La cama no está disponible", 409)

        existing = await self._active_assignment_for_hospitalization(
            hospitalization_id,
            lock=True,
        )
        if existing:
            raise DomainError("La internación ya tiene una cama activa", 409)

        if await self._active_assignment_for_bed(bed_id, lock=True):
            raise DomainError("La cama no está disponible", 409)

        if reservation is not None:
            self._complete_reservation(reservation, now)

        assignment = BedAssignment(
            hospitalization_id=hospitalization_id,
            bed_id=bed_id,
            started_at=now,
            assignment_reason=assignment_reason,
            assigned_by=assigned_by,
        )
        apply_bed_status(
            self.session,
            bed,
            BedStatus.OCCUPIED,
            changed_by=assigned_by,
            reason=assignment_reason,
            at=now,
            hospitalization_id=hospitalization_id,
            record_audit_event=False,
        )
        hospitalization.status = HospitalizationStatus.IN_PROGRESS
        hospitalization.admitted_at = hospitalization.admitted_at or now
        await move_to_bed_facility(self.session, hospitalization, bed)
        await self._mark_admission_admitted(
            hospitalization_id,
            hospitalization.admitted_at,
            arrival=arrival,
            at=now,
        )
        self.session.add(assignment)
        record_event(
            self.session,
            HospitalizationEventType.BED_ASSIGNED,
            hospitalization_id=hospitalization_id,
            bed_id=bed_id,
            patient_id=hospitalization.patient_id,
            actor=assigned_by,
            occurred_at=now,
            details={
                "reason": assignment_reason,
                "from_reservation": reservation is not None,
            },
        )
        await self.session.flush()
        return assignment

    async def _reservation_to_complete(
        self,
        bed: Bed,
        hospitalization_id: uuid.UUID,
    ) -> BedReservation | None:
        """Active reservation of this bed held for this hospitalization, if any."""

        if bed.status != BedStatus.RESERVED:
            return None
        reservation = await self.session.scalar(
            select(BedReservation)
            .where(
                BedReservation.bed_id == bed.id,
                BedReservation.status == BedReservationStatus.ACTIVE,
            )
            .with_for_update()
        )
        if reservation is None:
            return None
        if reservation.hospitalization_id != hospitalization_id:
            raise DomainError("La cama está reservada para otra internación", 409)
        return reservation

    @staticmethod
    def _complete_reservation(reservation: BedReservation, at: datetime) -> None:
        reservation.status = BedReservationStatus.COMPLETED
        reservation.completed_at = at

    async def _mark_admission_admitted(
        self,
        hospitalization_id: uuid.UUID,
        admitted_at: datetime,
        *,
        arrival: AdmissionArrivalCreate | None,
        at: datetime,
    ) -> None:
        admission = await self.session.scalar(
            select(Admission).where(Admission.hospitalization_id == hospitalization_id)
        )
        if not admission:
            return
        record_arrival(self.session, admission, arrival, at)
        if admission.status in {
            AdmissionStatus.ADMINISTRATIVE_DISCHARGE,
            AdmissionStatus.CANCELLED,
        }:
            return
        admission.status = AdmissionStatus.ADMITTED
        admission.admitted_at = admission.admitted_at or admitted_at

    async def _hospitalization_for_update(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(
            Hospitalization,
            hospitalization_id,
            with_for_update=True,
        )
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    @staticmethod
    def _validate_hospitalization_active(hospitalization: Hospitalization) -> None:
        if hospitalization.status not in ACTIVE_HOSPITALIZATION_STATUSES:
            raise DomainError("La internación no está activa", 409)

    async def _active_assignment_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
        lock: bool = False,
    ) -> BedAssignment | None:
        stmt = select(BedAssignment).where(
            BedAssignment.hospitalization_id == hospitalization_id,
            BedAssignment.ended_at.is_(None),
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def _active_assignment_for_bed(
        self,
        bed_id: uuid.UUID,
        lock: bool = False,
    ) -> BedAssignment | None:
        stmt = select(BedAssignment).where(
            BedAssignment.bed_id == bed_id,
            BedAssignment.ended_at.is_(None),
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def _lock_beds(
        self,
        first_bed_id: uuid.UUID,
        second_bed_id: uuid.UUID,
    ) -> dict[uuid.UUID, Bed]:
        bed_ids = sorted({first_bed_id, second_bed_id})
        rows = (
            await self.session.scalars(
                select(Bed).where(Bed.id.in_(bed_ids)).order_by(Bed.id).with_for_update()
            )
        ).all()
        return {bed.id: bed for bed in rows}
