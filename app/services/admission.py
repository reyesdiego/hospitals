"""Admission request workflow: the need for hospitalization and its authorization."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, integrity_conflict
from app.models.admission import (
    Admission,
    AdmissionConsent,
    AdmissionStatus,
    AuthorizationStatus,
    Episode,
    EpisodeStatus,
    episode_number,
)
from app.models.audit import HospitalizationEventType
from app.models.authorization import Authorization, AuthorizationState, AuthorizationType
from app.models.bed import Bed
from app.models.coverage import PatientCoverage
from app.models.facility import Facility
from app.models.hospitalization import Hospitalization
from app.models.patient import Patient
from app.models.professional import Professional
from app.models.service import Service
from app.schemas.domain import AdministrativeDischargeCreate, AdmissionCreate
from app.services.audit import record_event
from app.services.bed_assignment import BedAssignmentService
from app.services.hospitalization import HospitalizationService
from app.services.registry import build_coverage

#: Authorization outcomes that let the admission continue towards a bed.
CLEARED_AUTHORIZATION_STATUSES = {
    AuthorizationStatus.AUTHORIZED,
    AuthorizationStatus.NOT_REQUIRED,
}
_AUTHORIZATION_STATES = {
    AuthorizationStatus.PENDING: AuthorizationState.PENDING,
    AuthorizationStatus.AUTHORIZED: AuthorizationState.AUTHORIZED,
    AuthorizationStatus.REJECTED: AuthorizationState.REJECTED,
}


class AdmissionWorkflowService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, payload: AdmissionCreate) -> Admission:
        if not payload.identity_validated:
            raise DomainError("La identidad del paciente debe estar validada", 422)
        if not payload.duplicate_checked:
            raise DomainError("Debe verificarse la existencia de duplicados", 422)
        if payload.authorization_status == AuthorizationStatus.PENDING and payload.confirm_admission:
            raise DomainError("La autorización está pendiente", 409)
        if payload.authorization_status == AuthorizationStatus.REJECTED:
            raise DomainError("La autorización fue rechazada", 409)

        async with (
            integrity_conflict(self.session, "La cama solicitada ya no está disponible"),
            self.session.begin(),
        ):
            patient = await self.session.get(Patient, payload.patient_id)
            if not patient:
                raise DomainError("Paciente inexistente", 404)
            if payload.requesting_service_id and not await self.session.get(
                Service, payload.requesting_service_id
            ):
                raise DomainError("Servicio solicitante inexistente", 404)
            if payload.facility_id and not await self.session.get(Facility, payload.facility_id):
                raise DomainError("Centro sanitario inexistente", 404)
            if payload.responsible_physician_id and not await self.session.get(
                Professional, payload.responsible_physician_id
            ):
                raise DomainError("Profesional responsable inexistente", 404)

            coverage_id = await self._resolve_coverage(payload)
            now = datetime.now(UTC)
            facility_id = await self._resolve_facility(payload)

            episode = Episode(
                patient_id=payload.patient_id,
                facility_id=facility_id,
                episode_number=episode_number(now),
                status=EpisodeStatus.OPEN,
                reason=payload.admission_reason,
                opened_at=now,
            )
            self.session.add(episode)
            await self.session.flush()

            hospitalization = await HospitalizationService(
                self.session
            ).create_hospitalization(
                patient_id=payload.patient_id,
                admission_reason=payload.admission_reason,
                episode_id=episode.id,
                facility_id=facility_id,
                admission_type=payload.admission_type,
                responsible_service_id=payload.requesting_service_id,
                attending_physician_id=payload.responsible_physician_id,
                coverage_id=coverage_id,
                at=now,
            )

            status = AdmissionStatus.PENDING_AUTHORIZATION
            if payload.authorization_status in CLEARED_AUTHORIZATION_STATUSES:
                status = AdmissionStatus.PENDING_BED

            admission = Admission(
                patient_id=payload.patient_id,
                episode_id=episode.id,
                hospitalization_id=hospitalization.id,
                coverage_id=coverage_id,
                facility_id=facility_id,
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
                responsible_physician_id=payload.responsible_physician_id,
                presumptive_diagnosis=payload.presumptive_diagnosis,
                notes=payload.notes,
                requested_at=now,
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
            self._record_initial_authorization(admission, coverage_id, now)
            record_event(
                self.session,
                HospitalizationEventType.ADMISSION_REQUESTED,
                hospitalization_id=hospitalization.id,
                admission_id=admission.id,
                patient_id=payload.patient_id,
                occurred_at=now,
                details={
                    "origin": payload.origin.value,
                    "admission_type": payload.admission_type.value,
                },
            )

            if payload.requested_bed_id and payload.confirm_admission:
                await BedAssignmentService(self.session).assign(
                    hospitalization.id,
                    payload.requested_bed_id,
                    commit=False,
                    assignment_reason=payload.admission_reason,
                )
                admission.status = AdmissionStatus.ADMITTED
                admission.admitted_at = now
            return admission

    async def administrative_discharge(
        self,
        admission_id: uuid.UUID,
        payload: AdministrativeDischargeCreate,
    ) -> Admission:
        """Compatibility use case: closes the stay from the admission panel.

        Runs the missing lifecycle steps (clinical discharge, physical departure,
        administrative discharge) in order and in a single transaction; each one keeps its
        own timestamp and audit event.
        """

        async with self.session.begin():
            admission = await self.session.get(Admission, admission_id, with_for_update=True)
            if not admission:
                raise DomainError("Admisión inexistente", 404)
            if admission.status == AdmissionStatus.ADMINISTRATIVE_DISCHARGE:
                return admission

            now = datetime.now(UTC)
            if admission.hospitalization_id:
                hospitalization = await self.session.get(
                    Hospitalization,
                    admission.hospitalization_id,
                    with_for_update=True,
                )
                if hospitalization:
                    await HospitalizationService(self.session).complete_stay(
                        hospitalization,
                        payload,
                    )

            if admission.status != AdmissionStatus.ADMINISTRATIVE_DISCHARGE:
                admission.status = AdmissionStatus.ADMINISTRATIVE_DISCHARGE
                admission.administrative_discharged_at = now
                if payload.notes:
                    admission.notes = payload.notes
            if admission.episode_id:
                episode = await self.session.get(Episode, admission.episode_id)
                if episode and episode.status == EpisodeStatus.OPEN:
                    episode.status = EpisodeStatus.CLOSED
                    episode.closed_at = now
            return admission

    def _record_initial_authorization(
        self,
        admission: Admission,
        coverage_id: uuid.UUID | None,
        now: datetime,
    ) -> None:
        """Keep ``authorizations`` as the source of truth from the first moment."""

        state = _AUTHORIZATION_STATES.get(admission.authorization_status)
        if state is None:
            return
        self.session.add(
            Authorization(
                patient_id=admission.patient_id,
                admission_id=admission.id,
                hospitalization_id=admission.hospitalization_id,
                patient_coverage_id=coverage_id,
                authorization_type=AuthorizationType.ADMISSION,
                authorization_number=admission.authorization_number,
                status=state,
                requested_at=now,
                resolved_at=now if state != AuthorizationState.PENDING else None,
                authorized_at=now if state == AuthorizationState.AUTHORIZED else None,
                notes="Registrada junto con la solicitud de admisión",
            )
        )

    async def _resolve_facility(self, payload: AdmissionCreate) -> uuid.UUID | None:
        if payload.facility_id:
            return payload.facility_id
        if payload.requested_bed_id:
            bed = await self.session.get(Bed, payload.requested_bed_id)
            if not bed:
                raise DomainError("Cama solicitada inexistente", 404)
            return bed.facility_id
        return None

    async def _resolve_coverage(self, payload: AdmissionCreate) -> uuid.UUID | None:
        if payload.coverage_id and payload.coverage:
            raise DomainError("Informe coverage_id o coverage, no ambos", 422)
        if payload.coverage_id:
            coverage = await self.session.get(PatientCoverage, payload.coverage_id)
            if not coverage or coverage.patient_id != payload.patient_id:
                raise DomainError("Cobertura inexistente para el paciente", 404)
            return coverage.id
        if payload.coverage:
            coverage = await build_coverage(self.session, payload.patient_id, payload.coverage)
            await self.session.flush()
            return coverage.id
        return None
