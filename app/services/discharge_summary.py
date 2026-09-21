"""Resumen de alta (epicrisis): lo que pasó en la internación, en una hoja.

Es el documento que cierra la internación y el que lee el médico que recibe al paciente
después: por qué entró, qué se le encontró —los diagnósticos codificados en CIE-10—, qué
se le hizo y con qué se va. Se arma con lo que ya está cargado; no se escribe aparte,
porque un resumen que se escribe dos veces termina diciendo dos cosas distintas.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.account import Account
from app.models.bed import Bed, BedAssignment
from app.models.coverage import PatientCoverage
from app.models.diagnosis import DiagnosisStage, HospitalizationDiagnosis
from app.models.discharge import Discharge
from app.models.facility import Facility
from app.models.hospitalization import Hospitalization, HospitalizationServiceAssignment
from app.models.patient import Patient
from app.models.practice import HospitalizationPractice, PracticeOrderStatus
from app.models.prescription import DischargePrescription
from app.models.professional import Professional
from app.models.room import Room
from app.models.service import Service


@dataclass(frozen=True)
class PerformedPractice:
    code: str
    name: str
    performed_at: datetime | None
    quantity: Decimal


@dataclass(frozen=True)
class DischargeSummary:
    """Todo lo que va impreso, ya resuelto: el PDF no consulta la base."""

    facility_name: str
    patient_name: str
    patient_document: str
    coverage: str | None
    member_number: str | None
    service_name: str | None
    bed_label: str | None
    admitted_at: datetime | None
    discharged_at: datetime | None
    admission_reason: str
    discharge_type: str | None
    discharge_destination: str | None
    discharge_reason: str | None
    instructions: str | None
    physician: str
    admission_diagnoses: list[HospitalizationDiagnosis] = field(default_factory=list)
    discharge_diagnoses: list[HospitalizationDiagnosis] = field(default_factory=list)
    practices: list[PerformedPractice] = field(default_factory=list)
    prescriptions: list[DischargePrescription] = field(default_factory=list)

    @property
    def draft(self) -> bool:
        """Sin alta médica el resumen es provisorio, y el papel tiene que decirlo."""

        return self.discharged_at is None

    @property
    def length_of_stay_days(self) -> int | None:
        if not self.admitted_at:
            return None
        end = self.discharged_at or datetime.now(self.admitted_at.tzinfo)
        return max((end - self.admitted_at).days, 0)


async def build_summary(
    session: AsyncSession,
    hospitalization_id: uuid.UUID,
) -> DischargeSummary:
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

    # El servicio y la cama que tuvo: si ya se fue, los últimos.
    service_name = await session.scalar(
        select(Service.name)
        .join(
            HospitalizationServiceAssignment,
            HospitalizationServiceAssignment.service_id == Service.id,
        )
        .where(HospitalizationServiceAssignment.hospitalization_id == hospitalization_id)
        .order_by(HospitalizationServiceAssignment.started_at.desc())
        .limit(1)
    )
    location = (
        await session.execute(
            select(Bed, Room)
            .select_from(BedAssignment)
            .join(Bed, Bed.id == BedAssignment.bed_id)
            .outerjoin(Room, Room.id == Bed.room_id)
            .where(BedAssignment.hospitalization_id == hospitalization_id)
            .order_by(BedAssignment.started_at.desc())
            .limit(1)
        )
    ).first()
    bed_label = None
    if location:
        bed, room = location
        bed_label = f"{bed.code} - {bed.ward}"
        if room:
            bed_label = f"{bed_label}, habitación {room.code}"

    diagnoses = list(
        (
            await session.scalars(
                select(HospitalizationDiagnosis)
                .where(HospitalizationDiagnosis.hospitalization_id == hospitalization_id)
                # El principal primero: es el que encabeza el resumen.
                .order_by(
                    HospitalizationDiagnosis.role != "PRINCIPAL",
                    HospitalizationDiagnosis.diagnosed_at,
                )
            )
        ).all()
    )
    practices = [
        PerformedPractice(
            code=order.practice_code,
            name=order.practice_name,
            performed_at=order.performed_at,
            quantity=order.quantity,
        )
        for order in (
            await session.scalars(
                select(HospitalizationPractice)
                .where(
                    HospitalizationPractice.hospitalization_id == hospitalization_id,
                    HospitalizationPractice.status == PracticeOrderStatus.PERFORMED,
                )
                .order_by(HospitalizationPractice.performed_at)
            )
        ).all()
    ]
    prescriptions = list(
        (
            await session.scalars(
                select(DischargePrescription)
                .where(DischargePrescription.hospitalization_id == hospitalization_id)
                .order_by(DischargePrescription.kind, DischargePrescription.created_at)
            )
        ).all()
    )

    # Quién firma: el que ordenó el alta, y si no el médico de cabecera de la internación.
    physician = "-"
    signer_id = discharge.ordered_by_practitioner_id if discharge else None
    if signer_id:
        professional = await session.get(Professional, signer_id)
        if professional:
            physician = f"{professional.last_name}, {professional.first_name}"
    if physician == "-" and discharge and discharge.ordered_by:
        physician = discharge.ordered_by

    return DischargeSummary(
        facility_name=facility.name if facility else "Hospital",
        patient_name=(
            f"{patient.last_name}, {patient.first_name}" if patient else "Paciente"
        ),
        patient_document=(
            f"{patient.document_type} {patient.document_number}" if patient else "-"
        ),
        coverage=coverage.payer_name if coverage else None,
        member_number=coverage.member_number if coverage else None,
        service_name=service_name,
        bed_label=bed_label,
        admitted_at=hospitalization.admitted_at,
        discharged_at=hospitalization.clinically_discharged_at,
        admission_reason=hospitalization.admission_reason,
        discharge_type=discharge.discharge_type.value if discharge else None,
        discharge_destination=(
            discharge.destination.value if discharge and discharge.destination else None
        ),
        discharge_reason=discharge.discharge_reason if discharge else None,
        instructions=discharge.instructions if discharge else None,
        physician=physician,
        admission_diagnoses=[
            item for item in diagnoses if item.stage == DiagnosisStage.ADMISSION
        ],
        discharge_diagnoses=[
            item for item in diagnoses if item.stage == DiagnosisStage.DISCHARGE
        ],
        practices=practices,
        prescriptions=prescriptions,
    )
