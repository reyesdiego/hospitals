import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.admission import Admission, AdmissionStatus
from app.models.bed import (
    Bed,
    BedAssignment,
    BedStatus,
    BedTransfer,
    TransferStatus,
)
from app.models.hospitalization import Hospitalization, HospitalizationStatus

ACTIVE_HOSPITALIZATION_STATUSES = {
    HospitalizationStatus.PENDING_BED,
    HospitalizationStatus.IN_PROGRESS,
}
ASSIGNABLE_BED_STATUS = BedStatus.AVAILABLE


class BedAssignmentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def status_from_assignment(assignment: BedAssignment | None) -> BedStatus:
        if assignment is None:
            return BedStatus.AVAILABLE
        if assignment.status is not None:
            return assignment.status
        if assignment.hospitalization_id is not None:
            return BedStatus.OCCUPIED
        return BedStatus.AVAILABLE

    async def current_status(self, bed_id: uuid.UUID, at: datetime | None = None) -> BedStatus:
        session_get = getattr(self.session, "get", None)
        if session_get is not None:
            bed = await session_get(Bed, bed_id)
            if bed is not None:
                return bed.status

        at = at or datetime.now(UTC)
        assignment = await self.session.scalar(
            select(BedAssignment)
            .where(
                BedAssignment.bed_id == bed_id,
                BedAssignment.started_at <= at,
                (BedAssignment.ended_at.is_(None)) | (BedAssignment.ended_at > at),
            )
            .order_by(BedAssignment.started_at.desc())
        )
        return self.status_from_assignment(assignment)

    async def set_status(
        self,
        bed_id: uuid.UUID,
        status: BedStatus,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> BedAssignment | None:
        if status == BedStatus.OCCUPIED:
            raise DomainError("La ocupación se crea desde una internación", 409)

        async with self.session.begin():
            bed = await self.session.get(Bed, bed_id, with_for_update=True)
            if not bed:
                raise DomainError("Cama inexistente", 404)

            now = datetime.now(UTC)
            effective_start = started_at or now
            if ended_at is not None and ended_at <= effective_start:
                raise DomainError("El fin debe ser posterior al inicio", 422)

            active = await self._active_assignment_for_bed(bed_id, lock=True)
            if active and active.hospitalization_id is not None:
                raise DomainError("La cama está ocupada por una internación", 409)
            if active:
                active.ended_at = now

            bed.status = status
            if status == BedStatus.AVAILABLE:
                return active

            assignment = BedAssignment(
                bed_id=bed_id,
                status=status,
                started_at=effective_start,
                ended_at=ended_at,
            )
            self.session.add(assignment)
            await self.session.flush()
            return assignment

    async def assign(
        self,
        hospitalization_id: uuid.UUID,
        bed_id: uuid.UUID,
        commit: bool = True,
        assignment_reason: str | None = None,
        assigned_by: str | None = None,
    ) -> BedAssignment:
        if commit:
            try:
                async with self.session.begin():
                    return await self._assign_locked(
                        hospitalization_id,
                        bed_id,
                        assignment_reason=assignment_reason,
                        assigned_by=assigned_by,
                    )
            except IntegrityError as exc:
                await self.session.rollback()
                raise DomainError("La cama o la internación ya tienen una asignación activa", 409) from exc

        return await self._assign_locked(
            hospitalization_id,
            bed_id,
            assignment_reason=assignment_reason,
            assigned_by=assigned_by,
        )

    async def transfer(
        self,
        hospitalization_id: uuid.UUID,
        destination_bed_id: uuid.UUID,
        reason: str | None = None,
        requested_by: str | None = None,
        completed_by: str | None = None,
    ) -> BedTransfer:
        try:
            async with self.session.begin():
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
                if destination_bed.status != ASSIGNABLE_BED_STATUS:
                    raise DomainError("La cama destino no está disponible", 409)

                now = datetime.now(UTC)
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
                source_bed.status = BedStatus.PENDING_CLEANING

                new_assignment = BedAssignment(
                    hospitalization_id=hospitalization_id,
                    bed_id=destination_bed.id,
                    status=BedStatus.OCCUPIED,
                    started_at=now,
                    assignment_reason=reason,
                    assigned_by=completed_by,
                )
                destination_bed.status = BedStatus.OCCUPIED
                self.session.add_all([transfer, new_assignment])
                await self.session.flush()
                return transfer
        except IntegrityError as exc:
            await self.session.rollback()
            raise DomainError("La cama destino dejó de estar disponible", 409) from exc

    async def release(self, hospitalization_id: uuid.UUID) -> BedAssignment:
        async with self.session.begin():
            assignment = await self._active_assignment_for_hospitalization(
                hospitalization_id,
                lock=True,
            )
            if not assignment:
                raise DomainError("La internación no tiene una cama activa", 404)
            hospitalization = await self.session.get(
                Hospitalization,
                hospitalization_id,
                with_for_update=True,
            )
            bed = await self.session.get(Bed, assignment.bed_id, with_for_update=True)
            if not bed:
                raise DomainError("Cama inexistente", 404)

            now = datetime.now(UTC)
            assignment.ended_at = now
            bed.status = BedStatus.PENDING_CLEANING
            if hospitalization:
                hospitalization.status = HospitalizationStatus.CLINICALLY_DISCHARGED
                hospitalization.discharged_at = hospitalization.discharged_at or now
            await self.session.flush()
            return assignment

    async def _assign_locked(
        self,
        hospitalization_id: uuid.UUID,
        bed_id: uuid.UUID,
        assignment_reason: str | None = None,
        assigned_by: str | None = None,
    ) -> BedAssignment:
        hospitalization = await self._hospitalization_for_update(hospitalization_id)
        self._validate_hospitalization_active(hospitalization)

        bed = await self.session.get(Bed, bed_id, with_for_update=True)
        if not bed:
            raise DomainError("Cama inexistente", 404)
        if bed.status != ASSIGNABLE_BED_STATUS:
            raise DomainError("La cama no está disponible", 409)

        existing = await self._active_assignment_for_hospitalization(
            hospitalization_id,
            lock=True,
        )
        if existing:
            raise DomainError("La internación ya tiene una cama activa", 409)

        active_bed_assignment = await self._active_assignment_for_bed(bed_id, lock=True)
        if active_bed_assignment:
            raise DomainError("La cama no está disponible", 409)

        now = datetime.now(UTC)
        assignment = BedAssignment(
            hospitalization_id=hospitalization_id,
            bed_id=bed_id,
            status=BedStatus.OCCUPIED,
            started_at=now,
            assignment_reason=assignment_reason,
            assigned_by=assigned_by,
        )
        bed.status = BedStatus.OCCUPIED
        hospitalization.status = HospitalizationStatus.IN_PROGRESS
        hospitalization.admitted_at = hospitalization.admitted_at or now
        await self._mark_admission_admitted(hospitalization_id, hospitalization.admitted_at)
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def _mark_admission_admitted(
        self,
        hospitalization_id: uuid.UUID,
        admitted_at: datetime,
    ) -> None:
        admission = await self.session.scalar(
            select(Admission).where(Admission.hospitalization_id == hospitalization_id)
        )
        if not admission:
            return
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

    async def _lock_beds(self, first_bed_id: uuid.UUID, second_bed_id: uuid.UUID) -> dict[uuid.UUID, Bed]:
        bed_ids = sorted({first_bed_id, second_bed_id})
        rows = (
            await self.session.scalars(
                select(Bed)
                .where(Bed.id.in_(bed_ids))
                .order_by(Bed.id)
                .with_for_update()
            )
        ).all()
        return {bed.id: bed for bed in rows}
