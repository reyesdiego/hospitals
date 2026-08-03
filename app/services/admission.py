import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.admission import (
    Admission,
    AdmissionConsent,
    AdmissionStatus,
    AuthorizationStatus,
    Episode,
    EpisodeStatus,
    PatientCoverage,
)
from app.models.bed import BedStatus
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.patient import Patient
from app.models.service import Service
from app.schemas.domain import AdmissionCreate, AdministrativeDischargeCreate
from app.services.bed_assignment import BedAssignmentService


class AdmissionWorkflowService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, payload: AdmissionCreate) -> Admission:
        if not payload.identity_validated:
            raise DomainError("La identidad del paciente debe estar validada", 422)
        if not payload.duplicate_checked:
            raise DomainError("Debe verificarse la existencia de duplicados", 422)

        patient = await self.session.get(Patient, payload.patient_id)
        if not patient:
            raise DomainError("Paciente inexistente", 404)

        if payload.requesting_service_id:
            service = await self.session.get(Service, payload.requesting_service_id)
            if not service:
                raise DomainError("Servicio solicitante inexistente", 404)

        coverage_id = await self._resolve_coverage(payload)
        if payload.authorization_status == AuthorizationStatus.PENDING and payload.confirm_admission:
            raise DomainError("La autorización está pendiente", 409)
        if payload.authorization_status == AuthorizationStatus.REJECTED:
            raise DomainError("La autorización fue rechazada", 409)

        now = datetime.now(UTC)
        episode = Episode(
            patient_id=payload.patient_id,
            episode_number=self._episode_number(now),
            status=EpisodeStatus.OPEN,
            reason=payload.admission_reason,
            opened_at=now,
        )
        hospitalization = Hospitalization(
            patient_id=payload.patient_id,
            status=HospitalizationStatus.PENDING_BED,
            admission_reason=payload.admission_reason,
        )
        self.session.add_all([episode, hospitalization])
        await self.session.flush()

        status = AdmissionStatus.PENDING_AUTHORIZATION
        if payload.authorization_status in (
            AuthorizationStatus.AUTHORIZED,
            AuthorizationStatus.NOT_REQUIRED,
        ):
            status = AdmissionStatus.PENDING_BED

        admission = Admission(
            patient_id=payload.patient_id,
            episode_id=episode.id,
            hospitalization_id=hospitalization.id,
            coverage_id=coverage_id,
            requesting_service_id=payload.requesting_service_id,
            requested_bed_id=payload.requested_bed_id,
            origin=payload.origin,
            admission_type=payload.admission_type,
            status=status,
            identity_validated=payload.identity_validated,
            duplicate_checked=payload.duplicate_checked,
            authorization_status=payload.authorization_status,
            authorization_number=payload.authorization_number,
            responsible_contact_name=payload.responsible_contact_name,
            responsible_contact_phone=payload.responsible_contact_phone,
            responsible_contact_relationship=payload.responsible_contact_relationship,
            admission_reason=payload.admission_reason,
            responsible_physician=payload.responsible_physician,
            presumptive_diagnosis=payload.presumptive_diagnosis,
            notes=payload.notes,
        )
        self.session.add(admission)
        await self.session.flush()

        for consent in payload.consents:
            self.session.add(
                AdmissionConsent(
                    admission_id=admission.id,
                    consent_type=consent.consent_type,
                    signed_by=consent.signed_by,
                    signed_at=consent.signed_at or now,
                    notes=consent.notes,
                )
            )

        if payload.requested_bed_id and payload.confirm_admission:
            assignment = await BedAssignmentService(self.session).assign(
                hospitalization.id,
                payload.requested_bed_id,
                commit=False,
            )
            if assignment.status == BedStatus.OCCUPIED:
                admission.status = AdmissionStatus.ADMITTED
                admission.admitted_at = now
        elif payload.confirm_admission:
            admission.status = status

        await self.session.commit()
        await self.session.refresh(admission)
        return admission

    async def administrative_discharge(
        self,
        admission_id: uuid.UUID,
        payload: AdministrativeDischargeCreate,
    ) -> Admission:
        admission = await self.session.get(Admission, admission_id, with_for_update=True)
        if not admission:
            raise DomainError("Admisión inexistente", 404)
        if admission.status == AdmissionStatus.ADMINISTRATIVE_DISCHARGE:
            return admission

        now = datetime.now(UTC)
        admission.status = AdmissionStatus.ADMINISTRATIVE_DISCHARGE
        admission.administrative_discharged_at = now
        if payload.notes:
            admission.notes = payload.notes

        if admission.hospitalization_id:
            hospitalization = await self.session.get(Hospitalization, admission.hospitalization_id)
            if hospitalization and hospitalization.status != HospitalizationStatus.CLOSED:
                hospitalization.status = HospitalizationStatus.CLOSED
                hospitalization.discharged_at = hospitalization.discharged_at or now

        if admission.episode_id:
            episode = await self.session.get(Episode, admission.episode_id)
            if episode and episode.status != EpisodeStatus.CLOSED:
                episode.status = EpisodeStatus.CLOSED
                episode.closed_at = episode.closed_at or now

        await self.session.commit()
        await self.session.refresh(admission)
        return admission

    async def _resolve_coverage(self, payload: AdmissionCreate) -> uuid.UUID | None:
        if payload.coverage_id and payload.coverage:
            raise DomainError("Informe coverage_id o coverage, no ambos", 422)
        if payload.coverage_id:
            coverage = await self.session.get(PatientCoverage, payload.coverage_id)
            if not coverage or coverage.patient_id != payload.patient_id:
                raise DomainError("Cobertura inexistente para el paciente", 404)
            return coverage.id
        if payload.coverage:
            coverage = PatientCoverage(
                **payload.coverage.model_dump(exclude={"patient_id"}),
                patient_id=payload.patient_id,
            )
            self.session.add(coverage)
            await self.session.flush()
            return coverage.id
        return None

    @staticmethod
    def _episode_number(now: datetime) -> str:
        return f"EPI-{now:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8].upper()}"
