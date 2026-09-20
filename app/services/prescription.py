"""Recetas e indicaciones que se escriben al dar el alta médica."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DomainError
from app.core.users import STAFF, RequestUser
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.practice import MedicalPractice
from app.models.prescription import DischargePrescription, PrescriptionKind
from app.models.professional import Professional
from app.schemas.prescription import (
    DischargePrescriptionCreate,
    DischargePrescriptionUpdate,
)

if TYPE_CHECKING:  # pragma: no cover - solo para la anotación del documento
    from app.services.prescription_pdf import PrescriptionDocument

#: Se escriben mientras el paciente está internado y mientras se firma el alta médica.
#: Después del egreso administrativo la internación está cerrada y ya no se tocan.
EDITABLE_STATUSES = {
    HospitalizationStatus.PENDING_BED,
    HospitalizationStatus.IN_PROGRESS,
    HospitalizationStatus.DISCHARGE_PLANNED,
    HospitalizationStatus.CLINICALLY_DISCHARGED,
}


class DischargePrescriptionService:
    def __init__(self, session: AsyncSession, user: RequestUser = STAFF):
        self.session = session
        self.user = user

    async def list_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
    ) -> list[DischargePrescription]:
        await self._require_hospitalization(hospitalization_id)
        return list(
            (
                await self.session.scalars(
                    select(DischargePrescription)
                    .options(selectinload(DischargePrescription.practice))
                    .where(DischargePrescription.hospitalization_id == hospitalization_id)
                    .order_by(DischargePrescription.kind, DischargePrescription.created_at)
                )
            ).all()
        )

    async def add(
        self,
        hospitalization_id: uuid.UUID,
        payload: DischargePrescriptionCreate,
    ) -> DischargePrescription:
        async with self.session.begin():
            hospitalization = await self._require_editable(hospitalization_id)
            values = await self._values(payload)
            prescription = DischargePrescription(
                hospitalization_id=hospitalization.id,
                prescribed_at=datetime.now(UTC),
                prescribed_by_user_name=self.user.name,
                **values,
            )
            self.session.add(prescription)
            await self.session.flush()
            return await self._reload(prescription.id)

    async def update(
        self,
        hospitalization_id: uuid.UUID,
        prescription_id: uuid.UUID,
        payload: DischargePrescriptionUpdate,
    ) -> DischargePrescription:
        async with self.session.begin():
            await self._require_editable(hospitalization_id)
            prescription = await self._require_prescription(hospitalization_id, prescription_id)
            for field, value in (await self._values(payload)).items():
                setattr(prescription, field, value)
            await self.session.flush()
            return await self._reload(prescription.id)

    async def remove(self, hospitalization_id: uuid.UUID, prescription_id: uuid.UUID) -> None:
        async with self.session.begin():
            await self._require_editable(hospitalization_id)
            prescription = await self._require_prescription(hospitalization_id, prescription_id)
            await self.session.delete(prescription)

    async def _values(self, payload: DischargePrescriptionCreate) -> dict:
        """Resuelve el nombre de la práctica y valida lo que se indica."""

        description = payload.description.strip()
        practice: MedicalPractice | None = None
        if payload.practice_id:
            if payload.kind is not PrescriptionKind.PRACTICE:
                raise DomainError("La medicación no se elige del nomenclador", 422)
            practice = await self.session.get(MedicalPractice, payload.practice_id)
            if not practice:
                raise DomainError("Práctica inexistente", 404)
            # El nombre queda escrito: la indicación no cambia si el catálogo se edita.
            description = description or f"{practice.code} - {practice.name}"
        if not description:
            raise DomainError("Informe qué se le indica al paciente", 422)
        if payload.prescribed_by_id and not await self.session.get(
            Professional, payload.prescribed_by_id
        ):
            raise DomainError("Profesional inexistente", 404)

        return {
            "kind": payload.kind,
            "practice_id": payload.practice_id,
            "description": description,
            "presentation": payload.presentation,
            "dosage": payload.dosage,
            "quantity": payload.quantity,
            "duration_days": payload.duration_days,
            "instructions": payload.instructions,
            "prescribed_by_id": payload.prescribed_by_id,
        }

    async def _reload(self, prescription_id: uuid.UUID) -> DischargePrescription:
        prescription = await self.session.scalar(
            select(DischargePrescription)
            .options(selectinload(DischargePrescription.practice))
            .where(DischargePrescription.id == prescription_id)
        )
        if not prescription:
            raise DomainError("Indicación inexistente", 404)
        return prescription

    async def _require_hospitalization(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _require_editable(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        """Las recetas se escriben al dar el alta médica.

        Es la excepción al candado posterior al alta: el alta médica es el momento en que se
        indican, no un estado en el que ya no se toca nada. Se cierran con el egreso
        administrativo, cuando el paciente ya se fue con sus papeles.
        """

        hospitalization = await self._require_hospitalization(hospitalization_id)
        if hospitalization.status not in EDITABLE_STATUSES:
            raise DomainError(
                "La internación ya está cerrada: no admite cambios en las indicaciones",
                409,
            )
        return hospitalization

    async def _require_prescription(
        self,
        hospitalization_id: uuid.UUID,
        prescription_id: uuid.UUID,
    ) -> DischargePrescription:
        prescription = await self.session.get(DischargePrescription, prescription_id)
        if not prescription or prescription.hospitalization_id != hospitalization_id:
            raise DomainError("Indicación inexistente", 404)
        return prescription


async def build_document(
    session: AsyncSession,
    hospitalization_id: uuid.UUID,
) -> "PrescriptionDocument":
    """Junta lo que va impreso: paciente, cobertura, profesional y las indicaciones."""

    from app.models.account import Account
    from app.models.coverage import PatientCoverage
    from app.models.discharge import Discharge
    from app.models.facility import Facility
    from app.models.patient import Patient
    from app.services.prescription_pdf import PrescriptionDocument

    hospitalization = await session.get(Hospitalization, hospitalization_id)
    if not hospitalization:
        raise DomainError("Internación inexistente", 404)
    patient = await session.get(Patient, hospitalization.patient_id)
    facility = (
        await session.get(Facility, hospitalization.facility_id)
        if hospitalization.facility_id
        else None
    )
    discharge = await session.scalar(
        select(Discharge).where(Discharge.hospitalization_id == hospitalization_id)
    )
    account = await session.scalar(
        select(Account).where(Account.hospitalization_id == hospitalization_id)
    )
    coverage = (
        await session.get(PatientCoverage, account.coverage_id)
        if account and account.coverage_id
        else None
    )
    prescriptions = list(
        (
            await session.scalars(
                select(DischargePrescription)
                .where(DischargePrescription.hospitalization_id == hospitalization_id)
                .order_by(DischargePrescription.kind, DischargePrescription.created_at)
            )
        ).all()
    )

    # El profesional que firma: el que indicó, y si no el que ordenó el alta.
    physician = "-"
    signer_id = next(
        (item.prescribed_by_id for item in prescriptions if item.prescribed_by_id), None
    ) or (discharge.ordered_by_practitioner_id if discharge else None)
    if signer_id:
        professional = await session.get(Professional, signer_id)
        if professional:
            physician = f"{professional.last_name}, {professional.first_name}"
    if physician == "-" and discharge and discharge.ordered_by:
        physician = discharge.ordered_by

    return PrescriptionDocument(
        facility_name=facility.name if facility else "Hospital",
        patient_name=(
            f"{patient.last_name}, {patient.first_name}" if patient else "Paciente"
        ),
        patient_document=(
            f"{patient.document_type} {patient.document_number}" if patient else "-"
        ),
        coverage=coverage.payer_name if coverage else None,
        member_number=coverage.member_number if coverage else None,
        physician=physician,
        discharged_at=hospitalization.clinically_discharged_at,
        prescriptions=prescriptions,
    )
