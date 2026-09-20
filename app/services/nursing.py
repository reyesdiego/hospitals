"""Panel de enfermería: lo que el médico indicó y todavía hay que hacerle al paciente.

No es un circuito aparte del de prácticas: una inyección, una extracción o la colocación de
un Holter son prácticas del nomenclador marcadas como ``is_nursing_task``. El médico las
indica igual que cualquier otra y enfermería las ejecuta desde acá, así la práctica, su
cargo y el historial de la internación siguen siendo los mismos.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.users import STAFF, RequestUser
from app.models.bed import Bed, BedAssignment
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.patient import Patient
from app.models.practice import (
    HospitalizationPractice,
    MedicalPractice,
    PracticeOrderStatus,
)
from app.models.professional import Professional
from app.models.room import Room
from app.schemas.practice import (
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticePerformCreate,
)
from app.services.practice import HospitalizationPracticeService

#: Internaciones cuyas tareas tiene sentido mostrarle a enfermería.
ACTIVE_STATUSES = {
    HospitalizationStatus.PENDING_BED,
    HospitalizationStatus.IN_PROGRESS,
    HospitalizationStatus.DISCHARGE_PLANNED,
    HospitalizationStatus.CLINICALLY_DISCHARGED,
}


@dataclass(frozen=True)
class NursingTask:
    """Una tarea con lo que enfermería necesita para ejecutarla: quién, dónde y qué."""

    order: HospitalizationPractice
    patient: Patient
    hospitalization: Hospitalization
    prescribed_by: Professional | None
    bed_code: str | None
    room_code: str | None
    ward: str | None


class NursingTaskService:
    def __init__(self, session: AsyncSession, user: RequestUser = STAFF):
        self.session = session
        self.user = user
        self.practices = HospitalizationPracticeService(session, user)

    async def worklist(
        self,
        *,
        pending_only: bool = True,
        hospitalization_id: uuid.UUID | None = None,
        ward: str | None = None,
        on: date | None = None,
    ) -> list[NursingTask]:
        """Tareas de enfermería de las internaciones activas.

        Por defecto solo las pendientes, que es lo que hay que hacer ahora. ``on`` limita las
        ya resueltas a un día, para revisar lo hecho en el turno sin arrastrar el historial.
        """

        stmt = (
            select(HospitalizationPractice, Patient, Hospitalization, Bed, Room)
            .join(
                MedicalPractice,
                MedicalPractice.id == HospitalizationPractice.practice_id,
            )
            .join(
                Hospitalization,
                Hospitalization.id == HospitalizationPractice.hospitalization_id,
            )
            .join(Patient, Patient.id == Hospitalization.patient_id)
            # La cama es la que ocupa ahora: una tarea sin cama es de alguien esperando una.
            .outerjoin(
                BedAssignment,
                (BedAssignment.hospitalization_id == Hospitalization.id)
                & (BedAssignment.ended_at.is_(None)),
            )
            .outerjoin(Bed, Bed.id == BedAssignment.bed_id)
            .outerjoin(Room, Room.id == Bed.room_id)
            .where(
                MedicalPractice.is_nursing_task.is_(True),
                Hospitalization.status.in_(ACTIVE_STATUSES),
            )
            .order_by(HospitalizationPractice.prescribed_at)
        )
        if pending_only:
            stmt = stmt.where(HospitalizationPractice.status == PracticeOrderStatus.REQUESTED)
        if hospitalization_id:
            stmt = stmt.where(HospitalizationPractice.hospitalization_id == hospitalization_id)
        if ward:
            stmt = stmt.where(Bed.ward == ward)

        rows = (await self.session.execute(stmt)).all()
        tasks: list[NursingTask] = []
        for order, patient, hospitalization, bed, room in rows:
            if on and not _happened_on(order, on):
                continue
            prescribed_by = await self.session.get(Professional, order.prescribed_by_id)
            tasks.append(
                NursingTask(
                    order=order,
                    patient=patient,
                    hospitalization=hospitalization,
                    prescribed_by=prescribed_by,
                    bed_code=bed.code if bed else None,
                    room_code=room.code if room else None,
                    ward=bed.ward if bed else None,
                )
            )
        return tasks

    async def perform(
        self,
        order_id: uuid.UUID,
        payload: HospitalizationPracticePerformCreate,
    ) -> HospitalizationPractice:
        """Marcar la tarea como aplicada. Es la misma realización de siempre: genera el
        cargo y el evento en la internación."""

        hospitalization_id = await self._require_nursing_task(order_id)
        return await self.practices.perform(hospitalization_id, order_id, payload)

    async def cancel(
        self,
        order_id: uuid.UUID,
        payload: HospitalizationPracticeCancelCreate,
    ) -> HospitalizationPractice:
        hospitalization_id = await self._require_nursing_task(order_id)
        return await self.practices.cancel(hospitalization_id, order_id, payload)

    async def _require_nursing_task(self, order_id: uuid.UUID) -> uuid.UUID:
        """Valida la tarea y devuelve su internación.

        Devuelve el id y no la fila porque después de esta comprobación hay que cerrar la
        transacción implícita que abrieron estas lecturas: si no, el ``session.begin()`` del
        servicio de prácticas falla, y con él toda aplicación de una tarea.
        """

        order = await self.session.get(HospitalizationPractice, order_id)
        if not order:
            raise DomainError("Tarea inexistente", 404)
        practice = await self.session.get(MedicalPractice, order.practice_id)
        is_nursing = bool(practice and practice.is_nursing_task)
        hospitalization_id = order.hospitalization_id
        await self.session.rollback()

        if not is_nursing:
            raise DomainError(
                "La práctica no es una tarea de enfermería: regístrela desde la internación",
                409,
            )
        return hospitalization_id


def _happened_on(order: HospitalizationPractice, day: date) -> bool:
    """El día se compara en la zona del hospital.

    En UTC, un turno noche se parte en dos fechas y lo recién aplicado deja de aparecer en
    "lo de hoy" pasada la medianoche de Greenwich, que acá son las nueve de la noche.
    """

    moment = order.performed_at or order.cancelled_at or order.prescribed_at
    if not moment:
        return False
    return moment.astimezone(ZoneInfo(settings.timezone)).date() == day


def today_local() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()
