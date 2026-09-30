"""Hospitalization lifecycle.

The lifecycle moments are deliberately distinct events: administrative admission,
physical bed occupancy, clinical discharge, physical departure, administrative discharge
and financial closure never share a timestamp or a transition.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DomainError, integrity_conflict
from app.models.admission import (
    CLOSED_ADMISSION_STATUSES,
    Admission,
    AdmissionStatus,
    AdmissionType,
    AuthorizationStatus,
    Episode,
    EpisodeStatus,
    episode_number,
)
from app.models.audit import HospitalizationEventType
from app.models.bed import BedAssignment
from app.models.care_team import CareTeam, CareTeamMember, CareTeamRole
from app.models.diagnosis import DiagnosisStage
from app.models.discharge import (
    ACTIVE_DISCHARGE_PLAN_STATUSES,
    Discharge,
    DischargePlan,
    DischargePlanStatus,
)
from app.models.facility import Facility
from app.models.hospitalization import (
    CLINICALLY_ACTIVE_STATUSES,
    OPEN_HOSPITALIZATION_STATUSES,
    Hospitalization,
    HospitalizationServiceAssignment,
    HospitalizationStatus,
)
from app.models.patient import Patient
from app.models.professional import Professional
from app.models.service import Service
from app.schemas.domain import AdministrativeDischargeCreate, HospitalizationCreate
from app.schemas.workflow import (
    CareTeamMemberCreate,
    ClinicalDischargeCreate,
    DischargePlanCreate,
    PhysicalDepartureCreate,
    ServiceAssignmentCreate,
)
from app.services.access import require_patient_arrived
from app.services.account import (
    Account,
    mark_ready_for_review,
    open_account,
    patient_balance_for_account,
)
from app.services.audit import record_event
from app.services.bed_assignment import BedAssignmentService
from app.services.bed_reservation import BedReservationService
from app.services.diagnosis import record_diagnoses
from app.services.service_assignment import active_service_assignment, reassign_service


class HospitalizationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ creation
    async def create_from_admission(self, payload: HospitalizationCreate) -> Hospitalization:
        """Materialize the hospitalization of an admission request.

        There is no way to start an inpatient process without the request that justifies
        it: the patient, episode, facility, type and coverage all come from the request.
        """

        async with self.session.begin():
            admission = await self.session.get(
                Admission,
                payload.admission_id,
                with_for_update=True,
            )
            if not admission:
                raise DomainError("Admisión inexistente", 404)
            if admission.hospitalization_id:
                raise DomainError("La solicitud de admisión ya tiene una internación", 409)
            if admission.status in CLOSED_ADMISSION_STATUSES:
                raise DomainError("La solicitud de admisión no está vigente", 409)
            if admission.authorization_status == AuthorizationStatus.PENDING:
                raise DomainError("La autorización está pendiente", 409)

            now = datetime.now(UTC)
            episode_id = admission.episode_id
            if episode_id is None:
                episode = Episode(
                    patient_id=admission.patient_id,
                    facility_id=payload.facility_id or admission.facility_id,
                    episode_number=episode_number(now),
                    status=EpisodeStatus.OPEN,
                    reason=admission.admission_reason,
                    opened_at=now,
                )
                self.session.add(episode)
                await self.session.flush()
                episode_id = episode.id
                admission.episode_id = episode_id

            hospitalization = await self.create_hospitalization(
                patient_id=admission.patient_id,
                admission_reason=admission.admission_reason,
                episode_id=episode_id,
                facility_id=payload.facility_id or admission.facility_id,
                admission_type=admission.admission_type,
                responsible_service_id=payload.responsible_service_id
                or admission.requesting_service_id,
                attending_physician_id=payload.attending_physician_id
                or admission.responsible_physician_id,
                coverage_id=admission.coverage_id,
                admission_id=admission.id,
                at=now,
            )
            admission.hospitalization_id = hospitalization.id
            if admission.status == AdmissionStatus.PRE_ADMITTED:
                admission.status = AdmissionStatus.PENDING_BED
            return hospitalization

    async def cancel_pending(
        self,
        hospitalization_id: uuid.UUID,
        *,
        reason: str,
        actor: str | None = None,
    ) -> Hospitalization:
        """Cancel a hospitalization that never reached a bed (e.g. rejected authorization).

        Non-transactional: it runs inside the transaction of whoever rejected the request.
        """

        hospitalization = await self._for_update(hospitalization_id)
        if hospitalization.status not in {
            HospitalizationStatus.AWAITING_ARRIVAL,
            HospitalizationStatus.PENDING_BED,
        }:
            return hospitalization
        now = datetime.now(UTC)
        # Una cama reservada para una internación que no sigue queda libre para otro.
        await BedReservationService(self.session).cancel_active_for_hospitalization(
            hospitalization.id, now=now, actor=actor, reason=reason
        )
        hospitalization.status = HospitalizationStatus.CANCELLED
        await self.session.execute(
            update(HospitalizationServiceAssignment)
            .where(
                HospitalizationServiceAssignment.hospitalization_id == hospitalization.id,
                HospitalizationServiceAssignment.ended_at.is_(None),
            )
            .values(ended_at=now)
        )
        record_event(
            self.session,
            HospitalizationEventType.HOSPITALIZATION_CANCELLED,
            hospitalization_id=hospitalization.id,
            patient_id=hospitalization.patient_id,
            actor=actor,
            occurred_at=now,
            details={"reason": reason},
        )
        return hospitalization

    async def create_hospitalization(
        self,
        *,
        patient_id: uuid.UUID,
        admission_reason: str,
        episode_id: uuid.UUID | None = None,
        facility_id: uuid.UUID | None = None,
        admission_type: AdmissionType | None = None,
        responsible_service_id: uuid.UUID | None = None,
        attending_physician_id: uuid.UUID | None = None,
        coverage_id: uuid.UUID | None = None,
        admission_id: uuid.UUID | None = None,
        actor: str | None = None,
        at: datetime | None = None,
        awaiting_arrival: bool = False,
    ) -> Hospitalization:
        """Create the inpatient process plus the entities that always accompany it.

        Non-transactional: the caller owns the transaction so that creating a
        hospitalization from an admission request stays atomic.
        """

        now = at or datetime.now(UTC)
        if not await self.session.get(Patient, patient_id):
            raise DomainError("Paciente inexistente", 404)
        if episode_id and not await self.session.get(Episode, episode_id):
            raise DomainError("Episodio inexistente", 404)
        if facility_id and not await self.session.get(Facility, facility_id):
            raise DomainError("Centro sanitario inexistente", 404)
        if responsible_service_id and not await self.session.get(Service, responsible_service_id):
            raise DomainError("Servicio inexistente", 404)
        if attending_physician_id and not await self.session.get(
            Professional, attending_physician_id
        ):
            raise DomainError("Profesional inexistente", 404)

        hospitalization = Hospitalization(
            patient_id=patient_id,
            episode_id=episode_id,
            facility_id=facility_id,
            admission_type=admission_type,
            status=HospitalizationStatus.AWAITING_ARRIVAL
            if awaiting_arrival
            else HospitalizationStatus.PENDING_BED,
            admission_reason=admission_reason,
        )
        self.session.add(hospitalization)
        await self.session.flush()

        care_team = CareTeam(hospitalization_id=hospitalization.id)
        self.session.add(care_team)
        open_account(self.session, hospitalization, coverage_id=coverage_id, at=now)
        record_event(
            self.session,
            HospitalizationEventType.HOSPITALIZATION_CREATED,
            hospitalization_id=hospitalization.id,
            admission_id=admission_id,
            patient_id=patient_id,
            actor=actor,
            occurred_at=now,
            details={"admission_reason": admission_reason},
        )
        if responsible_service_id:
            await reassign_service(
                self.session,
                hospitalization,
                responsible_service_id,
                at=now,
                reason="Servicio responsable inicial",
                assigned_by=actor,
            )
        if attending_physician_id:
            await self.session.flush()
            self._add_member(
                care_team,
                hospitalization,
                practitioner_id=attending_physician_id,
                role=CareTeamRole.ATTENDING_PHYSICIAN,
                at=now,
                actor=actor,
                notes="Médico responsable de la admisión",
            )
        await self.session.flush()
        return hospitalization

    async def get(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    # --------------------------------------------------------- responsible service
    async def assign_service(
        self,
        hospitalization_id: uuid.UUID,
        payload: ServiceAssignmentCreate,
    ) -> HospitalizationServiceAssignment:
        async with (
            integrity_conflict(
                self.session,
                "La internación ya tiene un servicio responsable activo",
            ),
            self.session.begin(),
        ):
            hospitalization = await self._for_update(hospitalization_id)
            require_patient_arrived(hospitalization)
            if hospitalization.status not in OPEN_HOSPITALIZATION_STATUSES:
                raise DomainError("La internación no está activa", 409)
            if not await self.session.get(Service, payload.service_id):
                raise DomainError("Servicio inexistente", 404)

            current = await active_service_assignment(
                self.session,
                hospitalization_id,
                lock=True,
            )
            if current and current.service_id == payload.service_id:
                raise DomainError("El servicio ya es el responsable actual", 409)

            return await reassign_service(
                self.session,
                hospitalization,
                payload.service_id,
                at=datetime.now(UTC),
                reason=payload.reason,
                assigned_by=payload.assigned_by,
            )

    async def list_service_assignments(
        self,
        hospitalization_id: uuid.UUID,
    ) -> list[HospitalizationServiceAssignment]:
        await self.get(hospitalization_id)
        return list(
            (
                await self.session.scalars(
                    select(HospitalizationServiceAssignment)
                    .where(
                        HospitalizationServiceAssignment.hospitalization_id == hospitalization_id
                    )
                    .order_by(HospitalizationServiceAssignment.started_at.desc())
                )
            ).all()
        )

    # ----------------------------------------------------------------- care team
    async def care_team(self, hospitalization_id: uuid.UUID) -> CareTeam:
        await self.get(hospitalization_id)
        care_team = await self.session.scalar(
            select(CareTeam)
            .options(selectinload(CareTeam.members))
            .where(CareTeam.hospitalization_id == hospitalization_id)
        )
        if not care_team:
            raise DomainError("La internación no tiene equipo asistencial", 404)
        return care_team

    async def add_care_team_member(
        self,
        hospitalization_id: uuid.UUID,
        payload: CareTeamMemberCreate,
    ) -> CareTeamMember:
        async with (
            integrity_conflict(
                self.session,
                "El profesional ya cumple ese rol en el equipo asistencial",
            ),
            self.session.begin(),
        ):
            hospitalization = await self._for_update(hospitalization_id)
            require_patient_arrived(hospitalization)
            if hospitalization.status not in OPEN_HOSPITALIZATION_STATUSES:
                raise DomainError("La internación no está activa", 409)
            if not await self.session.get(Professional, payload.practitioner_id):
                raise DomainError("Profesional inexistente", 404)

            care_team = await self._care_team_for_update(hospitalization)
            member = self._add_member(
                care_team,
                hospitalization,
                practitioner_id=payload.practitioner_id,
                role=payload.role,
                at=datetime.now(UTC),
                actor=None,
                notes=payload.notes,
            )
            await self.session.flush()
            return member

    async def end_care_team_member(
        self,
        hospitalization_id: uuid.UUID,
        member_id: uuid.UUID,
        *,
        actor: str | None = None,
    ) -> CareTeamMember:
        async with self.session.begin():
            care_team = await self.session.scalar(
                select(CareTeam).where(CareTeam.hospitalization_id == hospitalization_id)
            )
            if not care_team:
                raise DomainError("La internación no tiene equipo asistencial", 404)
            require_patient_arrived(await self._for_update(hospitalization_id))
            member = await self.session.get(CareTeamMember, member_id, with_for_update=True)
            if not member or member.care_team_id != care_team.id:
                raise DomainError("Integrante inexistente", 404)
            if member.ended_at is not None:
                return member

            now = datetime.now(UTC)
            member.ended_at = now
            record_event(
                self.session,
                HospitalizationEventType.CARE_TEAM_MEMBER_ENDED,
                hospitalization_id=hospitalization_id,
                actor=actor,
                occurred_at=now,
                details={
                    "practitioner_id": str(member.practitioner_id),
                    "role": member.role.value,
                },
            )
            return member

    # ------------------------------------------------------------ discharge plan
    async def plan_discharge(
        self,
        hospitalization_id: uuid.UUID,
        payload: DischargePlanCreate,
    ) -> DischargePlan:
        async with (
            integrity_conflict(self.session, "La internación ya tiene un plan de alta activo"),
            self.session.begin(),
        ):
            hospitalization = await self._for_update(hospitalization_id)
            if hospitalization.status not in CLINICALLY_ACTIVE_STATUSES:
                raise DomainError("La internación no está en curso", 409)

            now = datetime.now(UTC)
            plan = DischargePlan(
                hospitalization_id=hospitalization_id,
                planned_date=payload.planned_date,
                destination=payload.destination,
                requires_transport=payload.requires_transport,
                requires_home_care=payload.requires_home_care,
                status=payload.status,
                created_by=payload.created_by,
                notes=payload.notes,
            )
            self.session.add(plan)
            # Planning a discharge neither releases the bed nor ends the hospitalization.
            if payload.status in ACTIVE_DISCHARGE_PLAN_STATUSES:
                hospitalization.status = HospitalizationStatus.DISCHARGE_PLANNED
            record_event(
                self.session,
                HospitalizationEventType.DISCHARGE_PLANNED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=payload.created_by,
                occurred_at=now,
                details={
                    "planned_date": payload.planned_date.isoformat()
                    if payload.planned_date
                    else None,
                    "destination": payload.destination.value,
                },
            )
            await self.session.flush()
            return plan

    async def discharge_plans(self, hospitalization_id: uuid.UUID) -> list[DischargePlan]:
        await self.get(hospitalization_id)
        return list(
            (
                await self.session.scalars(
                    select(DischargePlan)
                    .where(DischargePlan.hospitalization_id == hospitalization_id)
                    .order_by(DischargePlan.created_at.desc())
                )
            ).all()
        )

    # --------------------------------------------------------- clinical discharge
    async def clinical_discharge(
        self,
        hospitalization_id: uuid.UUID,
        payload: ClinicalDischargeCreate,
    ) -> Discharge:
        async with (
            integrity_conflict(self.session, "La internación ya tiene alta clínica"),
            self.session.begin(),
        ):
            hospitalization = await self._for_update(hospitalization_id)
            return await self._clinical_discharge(hospitalization, payload)

    async def _clinical_discharge(
        self,
        hospitalization: Hospitalization,
        payload: ClinicalDischargeCreate,
        *,
        at: datetime | None = None,
    ) -> Discharge:
        if hospitalization.status not in CLINICALLY_ACTIVE_STATUSES:
            raise DomainError(
                "La internación debe estar en curso para registrar el alta clínica",
                409,
            )
        if payload.ordered_by_practitioner_id and not await self.session.get(
            Professional, payload.ordered_by_practitioner_id
        ):
            raise DomainError("Profesional inexistente", 404)

        now = at or datetime.now(UTC)
        effective_at = payload.effective_at or now
        # Los diagnósticos de egreso son parte del alta: si alguno no cierra, no hay alta.
        await record_diagnoses(
            self.session,
            hospitalization,
            # Si no se dice otro, los de egreso los indica el médico que da el alta.
            [
                item
                if item.diagnosed_by_id
                else item.model_copy(
                    update={"diagnosed_by_id": payload.ordered_by_practitioner_id}
                )
                for item in payload.diagnoses
            ],
            stage=DiagnosisStage.DISCHARGE,
            at=now,
        )
        discharge = Discharge(
            hospitalization_id=hospitalization.id,
            discharge_type=payload.discharge_type,
            discharge_reason=payload.discharge_reason,
            destination=payload.destination,
            ordered_by=payload.ordered_by,
            ordered_by_practitioner_id=payload.ordered_by_practitioner_id,
            ordered_at=now,
            effective_at=effective_at,
            instructions=payload.instructions,
        )
        self.session.add(discharge)

        hospitalization.status = HospitalizationStatus.CLINICALLY_DISCHARGED
        hospitalization.clinically_discharged_at = effective_at
        # The bed stays OCCUPIED and the assignment active: the patient is still in it.
        await self.session.execute(
            update(DischargePlan)
            .where(
                DischargePlan.hospitalization_id == hospitalization.id,
                DischargePlan.status.in_(ACTIVE_DISCHARGE_PLAN_STATUSES),
            )
            .values(status=DischargePlanStatus.COMPLETED)
        )
        record_event(
            self.session,
            HospitalizationEventType.CLINICAL_DISCHARGE_COMPLETED,
            hospitalization_id=hospitalization.id,
            patient_id=hospitalization.patient_id,
            actor=payload.ordered_by,
            occurred_at=effective_at,
            details={
                "discharge_type": payload.discharge_type.value,
                "discharge_reason": payload.discharge_reason,
            },
        )
        await self.session.flush()
        return discharge

    async def discharge(self, hospitalization_id: uuid.UUID) -> Discharge:
        await self.get(hospitalization_id)
        discharge = await self.session.scalar(
            select(Discharge).where(Discharge.hospitalization_id == hospitalization_id)
        )
        if not discharge:
            raise DomainError("La internación no tiene alta clínica", 404)
        return discharge

    # -------------------------------------------------------- physical departure
    async def physical_departure(
        self,
        hospitalization_id: uuid.UUID,
        payload: PhysicalDepartureCreate,
    ) -> BedAssignment:
        async with self.session.begin():
            hospitalization = await self._for_update(hospitalization_id)
            return await self._physical_departure(hospitalization, payload)

    async def _physical_departure(
        self,
        hospitalization: Hospitalization,
        payload: PhysicalDepartureCreate,
    ) -> BedAssignment:
        if hospitalization.clinically_discharged_at is None:
            raise DomainError("La salida física requiere el alta clínica previa", 409)
        if hospitalization.physically_departed_at is not None:
            raise DomainError("La salida física ya fue registrada", 409)

        departed_at = payload.departed_at or datetime.now(UTC)
        assignment = await BedAssignmentService(self.session).end_active_assignment(
            hospitalization,
            at=departed_at,
            released_by=payload.released_by,
            reason=payload.notes,
        )
        hospitalization.physically_departed_at = departed_at
        record_event(
            self.session,
            HospitalizationEventType.PATIENT_PHYSICALLY_DEPARTED,
            hospitalization_id=hospitalization.id,
            bed_id=assignment.bed_id,
            patient_id=hospitalization.patient_id,
            actor=payload.released_by,
            occurred_at=departed_at,
            details={"notes": payload.notes},
        )
        await self.session.flush()
        return assignment

    # --------------------------------------------------- administrative discharge
    async def administrative_discharge(
        self,
        hospitalization_id: uuid.UUID,
        payload: AdministrativeDischargeCreate,
    ) -> Hospitalization:
        async with self.session.begin():
            hospitalization = await self._for_update(hospitalization_id)
            await self._administrative_discharge(hospitalization, payload)
            return hospitalization

    async def _administrative_discharge(
        self,
        hospitalization: Hospitalization,
        payload: AdministrativeDischargeCreate,
    ) -> None:
        if hospitalization.status in {
            HospitalizationStatus.ADMINISTRATIVELY_DISCHARGED,
            HospitalizationStatus.CLOSED,
        }:
            return
        if hospitalization.clinically_discharged_at is None:
            raise DomainError("El alta administrativa requiere el alta clínica previa", 409)
        if hospitalization.physically_departed_at is None:
            raise DomainError(
                "El alta administrativa requiere la salida física del paciente",
                409,
            )

        account = await self.session.scalar(
            select(Account)
            .where(Account.hospitalization_id == hospitalization.id)
            .with_for_update()
        )
        if account:
            await self._require_patient_account_settled(account)

        now = datetime.now(UTC)
        hospitalization.status = HospitalizationStatus.ADMINISTRATIVELY_DISCHARGED
        hospitalization.administratively_discharged_at = now

        # Open historical relations are closed, never deleted.
        await self.session.execute(
            update(HospitalizationServiceAssignment)
            .where(
                HospitalizationServiceAssignment.hospitalization_id == hospitalization.id,
                HospitalizationServiceAssignment.ended_at.is_(None),
            )
            .values(ended_at=now)
        )
        care_team_id = await self.session.scalar(
            select(CareTeam.id).where(CareTeam.hospitalization_id == hospitalization.id)
        )
        if care_team_id:
            await self.session.execute(
                update(CareTeamMember)
                .where(
                    CareTeamMember.care_team_id == care_team_id,
                    CareTeamMember.ended_at.is_(None),
                )
                .values(ended_at=now)
            )
        if hospitalization.episode_id:
            episode = await self.session.get(Episode, hospitalization.episode_id)
            if episode and episode.status == EpisodeStatus.OPEN:
                episode.status = EpisodeStatus.CLOSED
                episode.closed_at = now

        admission = await self.session.scalar(
            select(Admission)
            .where(Admission.hospitalization_id == hospitalization.id)
            .with_for_update()
        )
        if admission and admission.status != AdmissionStatus.ADMINISTRATIVE_DISCHARGE:
            admission.status = AdmissionStatus.ADMINISTRATIVE_DISCHARGE
            admission.administrative_discharged_at = now
            if payload.notes:
                admission.notes = payload.notes

        if account:
            # Billing continues on its own: the account is handed over, not closed.
            mark_ready_for_review(self.session, account, at=now, actor=payload.actor)

        record_event(
            self.session,
            HospitalizationEventType.ADMINISTRATIVE_DISCHARGE_COMPLETED,
            hospitalization_id=hospitalization.id,
            admission_id=admission.id if admission else None,
            patient_id=hospitalization.patient_id,
            actor=payload.actor,
            occurred_at=now,
            details={"notes": payload.notes},
        )
        await self.session.flush()

    # ------------------------------------------------------------------- legacy
    async def release_bed(self, hospitalization_id: uuid.UUID) -> BedAssignment:
        """Compatibility use case for ``POST /hospitalizations/{id}/release-bed``.

        Registers the clinical discharge (when it is missing) and the physical departure
        as the two separate events they are, inside a single transaction.
        """

        async with self.session.begin():
            hospitalization = await self._for_update(hospitalization_id)
            if hospitalization.status in CLINICALLY_ACTIVE_STATUSES:
                await self._clinical_discharge(
                    hospitalization,
                    ClinicalDischargeCreate(
                        discharge_reason="Alta clínica registrada al liberar la cama",
                    ),
                )
            return await self._physical_departure(
                hospitalization,
                PhysicalDepartureCreate(),
            )

    async def complete_stay(
        self,
        hospitalization: Hospitalization,
        payload: AdministrativeDischargeCreate,
    ) -> None:
        """Run the pending lifecycle steps up to the administrative discharge.

        Used by the admission-level compatibility endpoint; every step keeps its own
        timestamp and audit event.
        """

        if hospitalization.status in CLINICALLY_ACTIVE_STATUSES:
            await self._clinical_discharge(
                hospitalization,
                ClinicalDischargeCreate(
                    discharge_reason="Alta clínica registrada con el alta administrativa",
                    ordered_by=payload.actor,
                ),
            )
        if hospitalization.physically_departed_at is None and await self._has_active_assignment(
            hospitalization.id
        ):
            await self._physical_departure(
                hospitalization,
                PhysicalDepartureCreate(released_by=payload.actor),
            )
        await self._administrative_discharge(hospitalization, payload)

    async def _require_patient_account_settled(self, account: Account) -> None:
        """Sin el alta administrativa el paciente sigue siendo del hospital; una vez dada,
        cobrarle lo que puso de su bolsillo es correrlo por la calle. Lo del financiador no
        entra acá: eso se factura por convenio y se cobra después."""

        charged, paid, balance = await patient_balance_for_account(self.session, account.id)
        if balance <= 0:
            return
        raise DomainError(
            f"El alta administrativa requiere que el paciente cancele su saldo: adeuda "
            f"{balance} {account.currency} de {charged} a su cargo (pagado {paid})",
            409,
        )

    # ------------------------------------------------------------------ helpers
    async def _for_update(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(
            Hospitalization,
            hospitalization_id,
            with_for_update=True,
        )
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _has_active_assignment(self, hospitalization_id: uuid.UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(BedAssignment.id).where(
                    BedAssignment.hospitalization_id == hospitalization_id,
                    BedAssignment.ended_at.is_(None),
                )
            )
        )

    async def _care_team_for_update(self, hospitalization: Hospitalization) -> CareTeam:
        care_team = await self.session.scalar(
            select(CareTeam).where(CareTeam.hospitalization_id == hospitalization.id)
        )
        if care_team:
            return care_team
        care_team = CareTeam(hospitalization_id=hospitalization.id)
        self.session.add(care_team)
        await self.session.flush()
        return care_team

    def _add_member(
        self,
        care_team: CareTeam,
        hospitalization: Hospitalization,
        *,
        practitioner_id: uuid.UUID,
        role: CareTeamRole,
        at: datetime,
        actor: str | None,
        notes: str | None,
    ) -> CareTeamMember:
        member = CareTeamMember(
            care_team_id=care_team.id,
            practitioner_id=practitioner_id,
            role=role,
            started_at=at,
            notes=notes,
        )
        self.session.add(member)
        record_event(
            self.session,
            HospitalizationEventType.CARE_TEAM_MEMBER_ASSIGNED,
            hospitalization_id=hospitalization.id,
            patient_id=hospitalization.patient_id,
            actor=actor,
            occurred_at=at,
            details={"practitioner_id": str(practitioner_id), "role": role.value},
        )
        return member
