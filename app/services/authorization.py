"""Authorization of an admission request or of an ongoing hospitalization.

Coverage says who pays; an authorization is the payer's answer for one concrete event.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.admission import Admission, AdmissionStatus, AuthorizationStatus
from app.models.audit import HospitalizationEventType
from app.models.authorization import (
    OPEN_AUTHORIZATION_STATES,
    Authorization,
    AuthorizationState,
    AuthorizationType,
)
from app.models.coverage import PatientCoverage
from app.models.hospitalization import Hospitalization
from app.schemas.workflow import AuthorizationRequestCreate, AuthorizationResolveCreate
from app.services.audit import record_event
from app.services.hospitalization import HospitalizationService

#: Admission statuses whose flow still depends on the authorization outcome.
PENDING_ADMISSION_STATUSES = {
    AdmissionStatus.PRE_ADMITTED,
    AdmissionStatus.PENDING_AUTHORIZATION,
    AdmissionStatus.PENDING_BED,
}


class AuthorizationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def request_for_admission(
        self,
        admission_id: uuid.UUID,
        payload: AuthorizationRequestCreate,
    ) -> Authorization:
        async with self.session.begin():
            admission = await self.session.get(Admission, admission_id, with_for_update=True)
            if not admission:
                raise DomainError("Admisión inexistente", 404)
            if admission.status in {
                AdmissionStatus.ADMINISTRATIVE_DISCHARGE,
                AdmissionStatus.CANCELLED,
            }:
                raise DomainError("La admisión ya fue cerrada", 409)

            coverage_id = payload.patient_coverage_id or admission.coverage_id
            await self._validate_coverage(coverage_id, admission.patient_id)

            now = datetime.now(UTC)
            authorization = Authorization(
                patient_id=admission.patient_id,
                admission_id=admission.id,
                hospitalization_id=admission.hospitalization_id,
                patient_coverage_id=coverage_id,
                authorization_type=payload.authorization_type,
                authorization_number=payload.authorization_number,
                status=AuthorizationState.REQUESTED,
                requested_at=now,
                requested_by=payload.requested_by,
                valid_from=payload.valid_from,
                valid_until=payload.valid_until,
                notes=payload.notes,
            )
            self.session.add(authorization)

            if payload.authorization_type == AuthorizationType.ADMISSION:
                admission.authorization_status = AuthorizationStatus.PENDING
                if admission.status in PENDING_ADMISSION_STATUSES:
                    admission.status = AdmissionStatus.PENDING_AUTHORIZATION
            await self.session.flush()
            return authorization

    async def request_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
        payload: AuthorizationRequestCreate,
    ) -> Authorization:
        async with self.session.begin():
            hospitalization = await self.session.get(Hospitalization, hospitalization_id)
            if not hospitalization:
                raise DomainError("Internación inexistente", 404)

            admission = await self.session.scalar(
                select(Admission).where(Admission.hospitalization_id == hospitalization_id)
            )
            coverage_id = payload.patient_coverage_id or (admission.coverage_id if admission else None)
            await self._validate_coverage(coverage_id, hospitalization.patient_id)

            now = datetime.now(UTC)
            authorization = Authorization(
                patient_id=hospitalization.patient_id,
                admission_id=admission.id if admission else None,
                hospitalization_id=hospitalization_id,
                patient_coverage_id=coverage_id,
                authorization_type=payload.authorization_type,
                authorization_number=payload.authorization_number,
                status=AuthorizationState.REQUESTED,
                requested_at=now,
                requested_by=payload.requested_by,
                valid_from=payload.valid_from,
                valid_until=payload.valid_until,
                notes=payload.notes,
            )
            self.session.add(authorization)
            await self.session.flush()
            return authorization

    async def resolve(
        self,
        authorization_id: uuid.UUID,
        payload: AuthorizationResolveCreate,
    ) -> Authorization:
        if payload.status in OPEN_AUTHORIZATION_STATES:
            raise DomainError("Informe un estado resuelto de la autorización", 422)

        async with self.session.begin():
            authorization = await self.session.get(
                Authorization,
                authorization_id,
                with_for_update=True,
            )
            if not authorization:
                raise DomainError("Autorización inexistente", 404)
            if authorization.status not in OPEN_AUTHORIZATION_STATES:
                raise DomainError("La autorización ya fue resuelta", 409)

            now = datetime.now(UTC)
            authorization.status = payload.status
            authorization.resolved_at = now
            authorization.authorization_number = (
                payload.authorization_number or authorization.authorization_number
            )
            authorization.valid_from = payload.valid_from or authorization.valid_from
            authorization.valid_until = payload.valid_until or authorization.valid_until
            if payload.notes:
                authorization.notes = payload.notes
            if payload.status == AuthorizationState.AUTHORIZED:
                authorization.authorized_at = now

            await self._apply_to_admission(authorization, now)
            await self.session.flush()
            return authorization

    async def list_for_admission(self, admission_id: uuid.UUID) -> list[Authorization]:
        if not await self.session.get(Admission, admission_id):
            raise DomainError("Admisión inexistente", 404)
        return await self._list(Authorization.admission_id == admission_id)

    async def list_for_hospitalization(self, hospitalization_id: uuid.UUID) -> list[Authorization]:
        if not await self.session.get(Hospitalization, hospitalization_id):
            raise DomainError("Internación inexistente", 404)
        return await self._list(Authorization.hospitalization_id == hospitalization_id)

    async def _list(self, condition) -> list[Authorization]:
        return list(
            (
                await self.session.scalars(
                    select(Authorization)
                    .where(condition)
                    .order_by(Authorization.requested_at.desc())
                )
            ).all()
        )

    async def _apply_to_admission(self, authorization: Authorization, now: datetime) -> None:
        """An authorization decision moves the admission request forward."""

        if authorization.admission_id is None:
            return
        if authorization.authorization_type != AuthorizationType.ADMISSION:
            return
        admission = await self.session.get(
            Admission,
            authorization.admission_id,
            with_for_update=True,
        )
        if not admission:
            return

        if authorization.status == AuthorizationState.AUTHORIZED:
            admission.authorization_status = AuthorizationStatus.AUTHORIZED
            admission.authorization_number = (
                authorization.authorization_number or admission.authorization_number
            )
            if admission.status in PENDING_ADMISSION_STATUSES:
                admission.status = AdmissionStatus.PENDING_BED
            record_event(
                self.session,
                HospitalizationEventType.ADMISSION_AUTHORIZED,
                hospitalization_id=admission.hospitalization_id,
                admission_id=admission.id,
                patient_id=admission.patient_id,
                occurred_at=now,
                details={"authorization_number": authorization.authorization_number},
            )
        elif authorization.status == AuthorizationState.REJECTED:
            admission.authorization_status = AuthorizationStatus.REJECTED
            if admission.status in PENDING_ADMISSION_STATUSES:
                admission.status = AdmissionStatus.REJECTED
            if admission.hospitalization_id:
                # A rejected request must not leave an inpatient process waiting for a bed.
                await HospitalizationService(self.session).cancel_pending(
                    admission.hospitalization_id,
                    reason="Autorización rechazada",
                )
            record_event(
                self.session,
                HospitalizationEventType.ADMISSION_REJECTED,
                hospitalization_id=admission.hospitalization_id,
                admission_id=admission.id,
                patient_id=admission.patient_id,
                occurred_at=now,
                details={"notes": authorization.notes},
            )

    async def _validate_coverage(
        self,
        coverage_id: uuid.UUID | None,
        patient_id: uuid.UUID,
    ) -> None:
        if coverage_id is None:
            return
        coverage = await self.session.get(PatientCoverage, coverage_id)
        if not coverage or coverage.patient_id != patient_id:
            raise DomainError("Cobertura inexistente para el paciente", 404)
