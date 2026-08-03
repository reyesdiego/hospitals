import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.bed import Bed, BedAssignment, BedStatus
from app.models.hospitalization import Hospitalization, HospitalizationStatus


class BedAssignmentService:
    def __init__(self, session:AsyncSession): self.session=session

    @staticmethod
    def status_from_assignment(assignment: BedAssignment | None) -> BedStatus:
        if assignment is None:
            return BedStatus.AVAILABLE
        if assignment.status is not None:
            return assignment.status
        if assignment.hospitalization_id is not None:
            return BedStatus.OCCUPIED
        return BedStatus.AVAILABLE

    async def current_status(self,bed_id:uuid.UUID,at:datetime|None=None)->BedStatus:
        at=at or datetime.now(UTC)
        assignment=await self.session.scalar(
            select(BedAssignment)
            .where(
                BedAssignment.bed_id==bed_id,
                BedAssignment.started_at<=at,
                or_(BedAssignment.ended_at.is_(None),BedAssignment.ended_at>at),
            )
            .order_by(BedAssignment.started_at.desc())
        )
        return self.status_from_assignment(assignment)
    async def _has_overlap(self,bed_id:uuid.UUID,started_at:datetime,ended_at:datetime|None)->bool:
        conditions=[
            BedAssignment.bed_id==bed_id,
            or_(BedAssignment.ended_at.is_(None),BedAssignment.ended_at>started_at),
        ]
        if ended_at is not None:
            conditions.append(BedAssignment.started_at<ended_at)
        existing=await self.session.scalar(select(BedAssignment.id).where(and_(*conditions)).limit(1))
        return existing is not None
    async def set_status(self,bed_id:uuid.UUID,status:BedStatus,started_at:datetime|None=None,ended_at:datetime|None=None)->BedAssignment|None:
        bed=await self.session.get(Bed,bed_id,with_for_update=True)
        if not bed: raise DomainError("Cama inexistente",404)
        now=datetime.now(UTC)
        started_at=started_at or now
        if ended_at is not None and ended_at<=started_at: raise DomainError("El fin debe ser posterior al inicio",422)
        if status==BedStatus.OCCUPIED: raise DomainError("La ocupación se crea desde una internación",409)
        active=await self.session.scalar(
            select(BedAssignment)
            .where(BedAssignment.bed_id==bed_id,BedAssignment.ended_at.is_(None))
            .with_for_update()
        )
        if status==BedStatus.AVAILABLE:
            if active:
                active.ended_at=now
                await self.session.commit()
                await self.session.refresh(active)
                return active
            return None
        if await self._has_overlap(bed_id,started_at,ended_at): raise DomainError("La cama ya tiene un estado en ese rango",409)
        assignment=BedAssignment(bed_id=bed_id,status=status,started_at=started_at,ended_at=ended_at)
        self.session.add(assignment); await self.session.commit(); await self.session.refresh(assignment); return assignment
    async def assign(self,hospitalization_id:uuid.UUID,bed_id:uuid.UUID,commit:bool=True)->BedAssignment:
        hospitalization=await self.session.get(Hospitalization,hospitalization_id,with_for_update=True)
        if not hospitalization: raise DomainError("Internación inexistente",404)
        bed=await self.session.scalar(select(Bed).where(Bed.id==bed_id).with_for_update())
        if not bed: raise DomainError("Cama inexistente",404)
        if await self.current_status(bed_id)!=BedStatus.AVAILABLE: raise DomainError("La cama no está disponible",409)
        existing=await self.session.scalar(select(BedAssignment).where(BedAssignment.hospitalization_id==hospitalization_id,BedAssignment.ended_at.is_(None)))
        if existing: raise DomainError("La internación ya tiene una cama activa",409)
        now=datetime.now(UTC)
        assignment=BedAssignment(hospitalization_id=hospitalization_id,bed_id=bed_id,status=BedStatus.OCCUPIED,started_at=now)
        hospitalization.status=HospitalizationStatus.IN_PROGRESS; hospitalization.admitted_at=hospitalization.admitted_at or now
        self.session.add(assignment)
        if commit:
            await self.session.commit()
            await self.session.refresh(assignment)
        else:
            await self.session.flush()
        return assignment
    async def release(self,hospitalization_id:uuid.UUID)->BedAssignment:
        assignment=await self.session.scalar(select(BedAssignment).where(BedAssignment.hospitalization_id==hospitalization_id,BedAssignment.ended_at.is_(None)).with_for_update())
        if not assignment: raise DomainError("La internación no tiene una cama activa",404)
        hospitalization=await self.session.get(Hospitalization,hospitalization_id,with_for_update=True)
        now=datetime.now(UTC)
        assignment.ended_at=now
        cleaning=BedAssignment(bed_id=assignment.bed_id,status=BedStatus.PENDING_CLEANING,started_at=now)
        self.session.add(cleaning)
        if hospitalization: hospitalization.status=HospitalizationStatus.CLINICALLY_DISCHARGED
        await self.session.commit(); await self.session.refresh(assignment); return assignment
