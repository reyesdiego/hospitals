"""Medicación, tratamiento y notas de la internación."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.users import STAFF, RequestUser
from app.models.audit import HospitalizationEventType
from app.models.bed import Bed, BedAssignment
from app.models.hospitalization import (
    Hospitalization,
    HospitalizationServiceAssignment,
    HospitalizationStatus,
)
from app.models.patient import Patient
from app.models.professional import Professional
from app.models.room import Room
from app.models.service import Service
from app.models.treatment import (
    AdministrationStatus,
    ClinicalNoteStatus,
    HospitalizationNote,
    HospitalizationTreatment,
    TreatmentAdministration,
    TreatmentStatus,
)
from app.schemas.treatment import (
    AdministrationCreate,
    AdministrationVoidCreate,
    ClinicalNoteCreate,
    ClinicalNoteVoidCreate,
    TreatmentCreate,
    TreatmentStopCreate,
    TreatmentUpdate,
)
from app.services.access import require_editable
from app.services.audit import record_event
from app.services.medication_schedule import (
    DoseSlot,
    frequency_label,
    is_overdue,
    next_due,
    plan_doses,
)

#: Una indicación que ya se cortó no se vuelve a tocar: se indica de nuevo.
CLOSED_TREATMENT_STATUSES = {TreatmentStatus.SUSPENDED, TreatmentStatus.COMPLETED}

#: Internaciones cuya medicación tiene sentido mostrarle a enfermería en el pasillo.
ACTIVE_STAY_STATUSES = {
    HospitalizationStatus.PENDING_BED,
    HospitalizationStatus.IN_PROGRESS,
    HospitalizationStatus.DISCHARGE_PLANNED,
    HospitalizationStatus.CLINICALLY_DISCHARGED,
}


class HospitalizationTreatmentService:
    def __init__(self, session: AsyncSession, user: RequestUser = STAFF):
        self.session = session
        self.user = user

    async def list_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
        *,
        only_active: bool = False,
    ) -> list[HospitalizationTreatment]:
        await self._require_hospitalization(hospitalization_id)
        stmt = (
            select(HospitalizationTreatment)
            .where(HospitalizationTreatment.hospitalization_id == hospitalization_id)
            # Lo que se está dando ahora primero, y dentro de eso lo último indicado.
            .order_by(
                HospitalizationTreatment.status != TreatmentStatus.ACTIVE,
                HospitalizationTreatment.started_at.desc(),
            )
        )
        if only_active:
            stmt = stmt.where(HospitalizationTreatment.status == TreatmentStatus.ACTIVE)
        return list((await self.session.scalars(stmt)).all())

    async def add(
        self,
        hospitalization_id: uuid.UUID,
        payload: TreatmentCreate,
    ) -> HospitalizationTreatment:
        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Indicar medicación o tratamiento",
            )
            await self._require_professional(payload.prescribed_by_id)

            now = datetime.now(UTC)
            entry = HospitalizationTreatment(
                hospitalization_id=hospitalization_id,
                kind=payload.kind,
                description=payload.description.strip(),
                presentation=payload.presentation,
                dose=payload.dose,
                route=payload.route,
                # Si no se escribió, la frecuencia se lee del esquema: una sola verdad.
                frequency=payload.frequency or frequency_label(
                    payload.schedule_kind,
                    interval_hours=payload.interval_hours,
                    times_of_day=payload.times_of_day,
                ),
                schedule_kind=payload.schedule_kind,
                interval_hours=payload.interval_hours,
                times_of_day=payload.times_of_day,
                status=TreatmentStatus.ACTIVE,
                started_at=payload.started_at or now,
                prescribed_by_id=payload.prescribed_by_id,
                recorded_by_user_id=self.user.id,
                recorded_by_user_name=self.user.name,
                indication=payload.indication,
            )
            self.session.add(entry)
            record_event(
                self.session,
                HospitalizationEventType.TREATMENT_STARTED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=self.user.name,
                occurred_at=now,
                details={
                    "kind": payload.kind.value,
                    "description": entry.description,
                    "dose": payload.dose,
                },
            )
            await self.session.flush()
            return entry

    async def update(
        self,
        hospitalization_id: uuid.UUID,
        treatment_id: uuid.UUID,
        payload: TreatmentUpdate,
    ) -> HospitalizationTreatment:
        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Corregir una indicación",
            )
            entry = await self._require_entry(hospitalization_id, treatment_id)
            if entry.status in CLOSED_TREATMENT_STATUSES:
                raise DomainError(
                    "La indicación ya está cerrada: vuelva a indicarla en lugar de editarla",
                    409,
                )
            await self._require_professional(payload.prescribed_by_id)
            for field, value in payload.model_dump().items():
                setattr(entry, field, value)
            entry.frequency = payload.frequency or frequency_label(
                payload.schedule_kind,
                interval_hours=payload.interval_hours,
                times_of_day=payload.times_of_day,
            )
            await self.session.flush()
            return entry

    async def stop(
        self,
        hospitalization_id: uuid.UUID,
        treatment_id: uuid.UUID,
        payload: TreatmentStopCreate,
    ) -> HospitalizationTreatment:
        """Cortar lo que se estaba dando: suspendido o cumplido, siempre con fecha."""

        if payload.status not in CLOSED_TREATMENT_STATUSES:
            raise DomainError("Una indicación se cierra suspendida o cumplida", 422)

        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Suspender una indicación",
            )
            entry = await self._require_entry(hospitalization_id, treatment_id)
            if entry.status in CLOSED_TREATMENT_STATUSES:
                return entry

            now = payload.ended_at or datetime.now(UTC)
            if now < entry.started_at:
                raise DomainError("La indicación no puede terminar antes de empezar", 422)
            entry.status = payload.status
            entry.ended_at = now
            entry.end_reason = payload.reason
            record_event(
                self.session,
                HospitalizationEventType.TREATMENT_STOPPED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=self.user.name,
                occurred_at=now,
                details={
                    "description": entry.description,
                    "status": payload.status.value,
                    "reason": payload.reason,
                },
            )
            await self.session.flush()
            return entry

    async def _require_hospitalization(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _require_entry(
        self,
        hospitalization_id: uuid.UUID,
        treatment_id: uuid.UUID,
    ) -> HospitalizationTreatment:
        entry = await self.session.get(HospitalizationTreatment, treatment_id)
        if not entry or entry.hospitalization_id != hospitalization_id:
            raise DomainError("Indicación inexistente en la internación", 404)
        return entry

    async def _require_professional(self, professional_id: uuid.UUID | None) -> None:
        if professional_id and not await self.session.get(Professional, professional_id):
            raise DomainError("Profesional inexistente", 404)


class HospitalizationNoteService:
    def __init__(self, session: AsyncSession, user: RequestUser = STAFF):
        self.session = session
        self.user = user

    async def list_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
        *,
        include_void: bool = True,
    ) -> list[HospitalizationNote]:
        await self._require_hospitalization(hospitalization_id)
        stmt = (
            select(HospitalizationNote)
            .where(HospitalizationNote.hospitalization_id == hospitalization_id)
            # Lo último arriba: una historia se lee empezando por hoy.
            .order_by(HospitalizationNote.noted_at.desc())
        )
        if not include_void:
            stmt = stmt.where(HospitalizationNote.status == ClinicalNoteStatus.ACTIVE)
        return list((await self.session.scalars(stmt)).all())

    async def add(
        self,
        hospitalization_id: uuid.UUID,
        payload: ClinicalNoteCreate,
    ) -> HospitalizationNote:
        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Escribir una nota de evolución",
            )
            if payload.author_id and not await self.session.get(
                Professional, payload.author_id
            ):
                raise DomainError("Profesional inexistente", 404)
            if payload.service_id and not await self.session.get(Service, payload.service_id):
                raise DomainError("Servicio inexistente", 404)

            now = datetime.now(UTC)
            entry = HospitalizationNote(
                hospitalization_id=hospitalization_id,
                kind=payload.kind,
                status=ClinicalNoteStatus.ACTIVE,
                note=payload.note.strip(),
                author_id=payload.author_id,
                service_id=payload.service_id,
                recorded_by_user_id=self.user.id,
                recorded_by_user_name=self.user.name,
                noted_at=payload.noted_at or now,
            )
            self.session.add(entry)
            record_event(
                self.session,
                HospitalizationEventType.CLINICAL_NOTE_ADDED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=self.user.name,
                occurred_at=now,
                details={"kind": payload.kind.value},
            )
            await self.session.flush()
            return entry

    async def void(
        self,
        hospitalization_id: uuid.UUID,
        note_id: uuid.UUID,
        payload: ClinicalNoteVoidCreate,
    ) -> HospitalizationNote:
        """Anula una nota cargada por error. El texto queda: la historia no se borra."""

        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Anular una nota de evolución",
            )
            entry = await self._require_entry(hospitalization_id, note_id)
            if entry.status == ClinicalNoteStatus.VOID:
                return entry

            now = datetime.now(UTC)
            entry.status = ClinicalNoteStatus.VOID
            entry.voided_at = now
            entry.voided_by = payload.actor or self.user.name
            entry.void_reason = payload.reason
            record_event(
                self.session,
                HospitalizationEventType.CLINICAL_NOTE_VOIDED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=entry.voided_by,
                occurred_at=now,
                details={"kind": entry.kind.value, "reason": payload.reason},
            )
            await self.session.flush()
            return entry

    async def _require_hospitalization(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _require_entry(
        self,
        hospitalization_id: uuid.UUID,
        note_id: uuid.UUID,
    ) -> HospitalizationNote:
        entry = await self.session.get(HospitalizationNote, note_id)
        if not entry or entry.hospitalization_id != hospitalization_id:
            raise DomainError("Nota inexistente en la internación", 404)
        return entry


@dataclass(frozen=True)
class MedicationRound:
    """Una indicación activa con lo que enfermería necesita para darla."""

    treatment: HospitalizationTreatment
    patient: Patient
    ward: str | None
    room_code: str | None
    bed_code: str | None
    service_id: uuid.UUID | None
    service_name: str | None
    last_administered_at: datetime | None
    administrations: int
    #: La línea de tiempo de la ventana pedida, ya calculada.
    slots: list[DoseSlot]

    @property
    def next_due_at(self) -> datetime | None:
        return next_due(self.slots)

    @property
    def overdue(self) -> bool:
        return is_overdue(self.slots)


class TreatmentAdministrationService:
    """El registro de administración: lo que enfermería efectivamente le dio al paciente.

    La indicación dice lo que hay que hacer; esto dice lo que pasó. Una toma no se borra:
    se anula con su motivo, y una que no se pudo dar se registra igual, omitida y con la
    razón, porque la omisión también es información clínica.
    """

    def __init__(self, session: AsyncSession, user: RequestUser = STAFF):
        self.session = session
        self.user = user

    async def list_for_treatment(
        self,
        hospitalization_id: uuid.UUID,
        treatment_id: uuid.UUID,
    ) -> list[TreatmentAdministration]:
        await self._require_treatment(hospitalization_id, treatment_id)
        return list(
            (
                await self.session.scalars(
                    select(TreatmentAdministration)
                    .where(TreatmentAdministration.treatment_id == treatment_id)
                    .order_by(TreatmentAdministration.administered_at.desc())
                )
            ).all()
        )

    async def register(
        self,
        hospitalization_id: uuid.UUID,
        treatment_id: uuid.UUID,
        payload: AdministrationCreate,
    ) -> TreatmentAdministration:
        if payload.status == AdministrationStatus.VOID:
            raise DomainError("Una toma se registra dada u omitida", 422)

        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Registrar una toma",
            )
            treatment = await self._require_treatment(hospitalization_id, treatment_id)

            now = payload.administered_at or datetime.now(UTC)
            if now < treatment.started_at:
                raise DomainError(
                    "La toma no puede ser anterior al inicio de la indicación",
                    422,
                )
            # Una indicación cerrada acepta la toma que quedó sin cargar, no una nueva.
            if (
                treatment.status in CLOSED_TREATMENT_STATUSES
                and treatment.ended_at
                and now > treatment.ended_at
            ):
                raise DomainError(
                    "La indicación ya está cerrada: no se pueden registrar tomas posteriores",
                    409,
                )
            if (
                payload.status == AdministrationStatus.OMITTED
                and not (payload.omission_reason or "").strip()
            ):
                raise DomainError("Una toma omitida necesita su motivo", 422)
            if payload.administered_by_id and not await self.session.get(
                Professional, payload.administered_by_id
            ):
                raise DomainError("Profesional inexistente", 404)

            entry = TreatmentAdministration(
                treatment_id=treatment.id,
                hospitalization_id=hospitalization_id,
                status=payload.status,
                administered_at=now,
                # Lo habitual es dar lo indicado: la dosis de la indicación es el default.
                dose=payload.dose or treatment.dose,
                route=treatment.route,
                omission_reason=payload.omission_reason,
                administered_by_id=payload.administered_by_id,
                recorded_by_user_id=self.user.id,
                recorded_by_user_name=self.user.name,
                notes=payload.notes,
            )
            self.session.add(entry)
            record_event(
                self.session,
                HospitalizationEventType.TREATMENT_ADMINISTERED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=self.user.name,
                occurred_at=now,
                details={
                    "description": treatment.description,
                    "status": payload.status.value,
                    "dose": entry.dose,
                    "reason": payload.omission_reason,
                },
            )
            await self.session.flush()
            return entry

    async def void(
        self,
        hospitalization_id: uuid.UUID,
        treatment_id: uuid.UUID,
        administration_id: uuid.UUID,
        payload: AdministrationVoidCreate,
    ) -> TreatmentAdministration:
        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Anular una toma",
            )
            await self._require_treatment(hospitalization_id, treatment_id)
            entry = await self.session.get(TreatmentAdministration, administration_id)
            if not entry or entry.treatment_id != treatment_id:
                raise DomainError("Toma inexistente en la indicación", 404)
            if entry.status == AdministrationStatus.VOID:
                return entry

            now = datetime.now(UTC)
            entry.status = AdministrationStatus.VOID
            entry.voided_at = now
            entry.voided_by = payload.actor or self.user.name
            entry.void_reason = payload.reason
            await self.session.flush()
            return entry

    async def medication_round(
        self,
        *,
        hospitalization_id: uuid.UUID | None = None,
        service_id: uuid.UUID | None = None,
        ward: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        overdue_only: bool = False,
    ) -> list[MedicationRound]:
        """Lo que hay que dar en el pasillo: indicaciones activas de internaciones
        activas, con sus horarios calculados dentro de la ventana pedida.

        Por omisión la ventana son las doce horas para atrás y las doce para adelante:
        el turno que se está haciendo y el que viene.
        """

        now = datetime.now(UTC)
        window_start = window_start or now - timedelta(hours=12)
        window_end = window_end or now + timedelta(hours=12)

        given = (
            select(
                TreatmentAdministration.treatment_id.label("treatment_id"),
                func.max(TreatmentAdministration.administered_at).label("last_at"),
                func.count().label("total"),
            )
            .where(TreatmentAdministration.status != AdministrationStatus.VOID)
            .group_by(TreatmentAdministration.treatment_id)
            .subquery()
        )
        stmt = (
            select(
                HospitalizationTreatment,
                Patient,
                Bed,
                Room,
                Service.id,
                Service.name,
                given.c.last_at,
                given.c.total,
            )
            .join(
                Hospitalization,
                Hospitalization.id == HospitalizationTreatment.hospitalization_id,
            )
            .join(Patient, Patient.id == Hospitalization.patient_id)
            .outerjoin(
                BedAssignment,
                (BedAssignment.hospitalization_id == Hospitalization.id)
                & (BedAssignment.ended_at.is_(None)),
            )
            .outerjoin(Bed, Bed.id == BedAssignment.bed_id)
            .outerjoin(Room, Room.id == Bed.room_id)
            .outerjoin(
                HospitalizationServiceAssignment,
                (HospitalizationServiceAssignment.hospitalization_id == Hospitalization.id)
                & (HospitalizationServiceAssignment.ended_at.is_(None)),
            )
            .outerjoin(Service, Service.id == HospitalizationServiceAssignment.service_id)
            .outerjoin(given, given.c.treatment_id == HospitalizationTreatment.id)
            .where(
                HospitalizationTreatment.status == TreatmentStatus.ACTIVE,
                Hospitalization.status.in_(ACTIVE_STAY_STATUSES),
            )
            # Lo que hace más que esperó: primero lo que nunca se dio.
            .order_by(given.c.last_at.nulls_first(), HospitalizationTreatment.started_at)
        )
        if hospitalization_id:
            stmt = stmt.where(
                HospitalizationTreatment.hospitalization_id == hospitalization_id
            )
        if service_id:
            stmt = stmt.where(HospitalizationServiceAssignment.service_id == service_id)
        if ward:
            stmt = stmt.where(Bed.ward == ward)

        rows = (await self.session.execute(stmt)).all()
        administrations = await self._administrations_by_treatment(
            [row[0].id for row in rows],
            since=window_start,
        )
        rounds = [
            MedicationRound(
                treatment=treatment,
                patient=patient,
                ward=bed.ward if bed else None,
                room_code=room.code if room else None,
                bed_code=bed.code if bed else None,
                service_id=service_id_row,
                service_name=service_name,
                last_administered_at=last_at,
                administrations=total or 0,
                slots=plan_doses(
                    treatment,
                    administrations.get(treatment.id, []),
                    window_start=window_start,
                    window_end=window_end,
                    now=now,
                    timezone=settings.timezone,
                ),
            )
            for treatment, patient, bed, room, service_id_row, service_name, last_at, total in rows
        ]
        if overdue_only:
            rounds = [item for item in rounds if item.overdue]
        # Lo vencido primero y, dentro de eso, lo que hace más que espera.
        return sorted(
            rounds,
            key=lambda item: (
                not item.overdue,
                item.next_due_at or datetime.max.replace(tzinfo=UTC),
            ),
        )

    async def _administrations_by_treatment(
        self,
        treatment_ids: list[uuid.UUID],
        *,
        since: datetime,
    ) -> dict[uuid.UUID, list[TreatmentAdministration]]:
        """Las tomas que hacen falta para calcular: las de la ventana y la última previa,
        que es la que ancla el próximo horario de un esquema por intervalo."""

        if not treatment_ids:
            return {}
        entries = (
            await self.session.scalars(
                select(TreatmentAdministration)
                .where(TreatmentAdministration.treatment_id.in_(treatment_ids))
                .order_by(TreatmentAdministration.administered_at)
            )
        ).all()
        grouped: dict[uuid.UUID, list[TreatmentAdministration]] = {}
        for entry in entries:
            grouped.setdefault(entry.treatment_id, []).append(entry)
        return grouped

    async def _require_hospitalization(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _require_treatment(
        self,
        hospitalization_id: uuid.UUID,
        treatment_id: uuid.UUID,
    ) -> HospitalizationTreatment:
        treatment = await self.session.get(HospitalizationTreatment, treatment_id)
        if not treatment or treatment.hospitalization_id != hospitalization_id:
            raise DomainError("Indicación inexistente en la internación", 404)
        return treatment
