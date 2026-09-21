"""Historia clínica del paciente: todo lo suyo, junto y ordenado en el tiempo.

La internación es la unidad con la que trabaja el resto del sistema; acá se da vuelta y
se mira por paciente, que es lo que necesita el médico que lo atiende hoy: qué le pasó,
qué se le diagnosticó, qué se le hizo, con qué se fue y qué debe.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.account import (
    Account,
    ChargeItem,
    ChargeItemStatus,
    Payment,
    PaymentStatus,
    ResponsibleParty,
)
from app.models.bed import Bed, BedAssignment
from app.models.coverage import PatientCoverage
from app.models.diagnosis import DiagnosisRole, DiagnosisStage, HospitalizationDiagnosis
from app.models.facility import Facility
from app.models.hospitalization import (
    OPEN_HOSPITALIZATION_STATUSES,
    Hospitalization,
    HospitalizationServiceAssignment,
)
from app.models.patient import Patient
from app.models.practice import (
    HospitalizationPractice,
    MedicalPractice,
    PracticeChapter,
    PracticeOrderStatus,
    PracticeType,
)
from app.models.prescription import DischargePrescription
from app.models.room import Room
from app.models.service import Service
from app.models.treatment import (
    ClinicalNoteStatus,
    HospitalizationNote,
    HospitalizationTreatment,
)

#: Lo que se cuenta como consulta, por oposición a las prácticas hechas en la internación.
CONSULTATION_CHAPTERS = {PracticeChapter.CONSULTAS}
CONSULTATION_TYPES = {PracticeType.CONSULTA}


@dataclass(frozen=True)
class StayLocation:
    facility_name: str | None
    service_name: str | None
    bed_label: str | None


async def _locations(
    session: AsyncSession,
    hospitalization_ids: list[uuid.UUID],
) -> dict[uuid.UUID, StayLocation]:
    """Centro, servicio y cama de cada internación, en una consulta por cosa."""

    if not hospitalization_ids:
        return {}

    facilities = dict(
        (
            await session.execute(
                select(Hospitalization.id, Facility.name)
                .join(Facility, Facility.id == Hospitalization.facility_id)
                .where(Hospitalization.id.in_(hospitalization_ids))
            )
        ).all()
    )
    # El último servicio y la última cama: la internación pudo pasar por varios.
    services = dict(
        (
            await session.execute(
                select(
                    HospitalizationServiceAssignment.hospitalization_id,
                    func.max(Service.name),
                )
                .join(Service, Service.id == HospitalizationServiceAssignment.service_id)
                .where(
                    HospitalizationServiceAssignment.hospitalization_id.in_(
                        hospitalization_ids
                    )
                )
                .group_by(HospitalizationServiceAssignment.hospitalization_id)
            )
        ).all()
    )
    beds: dict[uuid.UUID, str] = {}
    for hospitalization_id, code, ward, room_code in (
        await session.execute(
            select(BedAssignment.hospitalization_id, Bed.code, Bed.ward, Room.code)
            .join(Bed, Bed.id == BedAssignment.bed_id)
            .outerjoin(Room, Room.id == Bed.room_id)
            .where(BedAssignment.hospitalization_id.in_(hospitalization_ids))
            .order_by(BedAssignment.started_at)
        )
    ).all():
        label = f"{code} - {ward}"
        if room_code:
            label = f"{label}, habitación {room_code}"
        beds[hospitalization_id] = label

    return {
        hospitalization_id: StayLocation(
            facility_name=facilities.get(hospitalization_id),
            service_name=services.get(hospitalization_id),
            bed_label=beds.get(hospitalization_id),
        )
        for hospitalization_id in hospitalization_ids
    }


@dataclass(frozen=True)
class PatientRecord:
    patient: Patient
    coverages: list[PatientCoverage]
    hospitalizations: list[Hospitalization]
    locations: dict[uuid.UUID, StayLocation]
    diagnoses: list[HospitalizationDiagnosis]
    practices: list[tuple[HospitalizationPractice, bool, Decimal | None]]
    prescriptions: list[DischargePrescription]
    treatments: list[HospitalizationTreatment]
    notes: list[HospitalizationNote]
    payments: list[Payment]
    payment_stays: dict[uuid.UUID, uuid.UUID]
    patient_charged: Decimal
    paid: Decimal

    @property
    def balance(self) -> Decimal:
        return max(self.patient_charged - self.paid, Decimal(0))

    @property
    def open_stays(self) -> int:
        return sum(
            1
            for stay in self.hospitalizations
            if stay.status in OPEN_HOSPITALIZATION_STATUSES
        )

    def principal_diagnosis(self, hospitalization_id: uuid.UUID) -> str | None:
        """El de egreso manda; mientras no exista, el de ingreso."""

        for stage in (DiagnosisStage.DISCHARGE, DiagnosisStage.ADMISSION):
            for entry in self.diagnoses:
                if (
                    entry.hospitalization_id == hospitalization_id
                    and entry.stage == stage
                    and entry.role == DiagnosisRole.PRINCIPAL
                ):
                    return f"{entry.code} - {entry.description}"
        return None


def length_of_stay_days(stay: Hospitalization) -> int | None:
    if not stay.admitted_at:
        return None
    end = stay.clinically_discharged_at or datetime.now(UTC)
    return max((end - stay.admitted_at).days, 0)


async def build_record(session: AsyncSession, patient_id: uuid.UUID) -> PatientRecord:
    patient = await session.get(Patient, patient_id)
    if not patient:
        raise DomainError("Paciente inexistente", 404)

    coverages = list(
        (
            await session.scalars(
                select(PatientCoverage)
                .where(PatientCoverage.patient_id == patient_id)
                .order_by(PatientCoverage.created_at)
            )
        ).all()
    )
    hospitalizations = list(
        (
            await session.scalars(
                select(Hospitalization)
                .where(Hospitalization.patient_id == patient_id)
                # Lo último primero: es por donde se empieza a leer una historia.
                .order_by(Hospitalization.created_at.desc())
            )
        ).all()
    )
    stay_ids = [stay.id for stay in hospitalizations]
    if not stay_ids:
        return PatientRecord(
            patient=patient,
            coverages=coverages,
            hospitalizations=[],
            locations={},
            diagnoses=[],
            practices=[],
            prescriptions=[],
            treatments=[],
            notes=[],
            payments=[],
            payment_stays={},
            patient_charged=Decimal(0),
            paid=Decimal(0),
        )

    diagnoses = list(
        (
            await session.scalars(
                select(HospitalizationDiagnosis)
                .where(HospitalizationDiagnosis.hospitalization_id.in_(stay_ids))
                .order_by(HospitalizationDiagnosis.diagnosed_at.desc())
            )
        ).all()
    )
    practices = [
        (
            order,
            chapter in CONSULTATION_CHAPTERS or practice_type in CONSULTATION_TYPES,
            amount,
        )
        for order, chapter, practice_type, amount in (
            await session.execute(
                select(
                    HospitalizationPractice,
                    MedicalPractice.chapter,
                    MedicalPractice.practice_type,
                    ChargeItem.amount,
                )
                .join(
                    MedicalPractice,
                    MedicalPractice.id == HospitalizationPractice.practice_id,
                )
                .outerjoin(
                    ChargeItem,
                    ChargeItem.id == HospitalizationPractice.charge_item_id,
                )
                .where(HospitalizationPractice.hospitalization_id.in_(stay_ids))
                .order_by(HospitalizationPractice.prescribed_at.desc())
            )
        ).all()
    ]
    prescriptions = list(
        (
            await session.scalars(
                select(DischargePrescription)
                .where(DischargePrescription.hospitalization_id.in_(stay_ids))
                .order_by(DischargePrescription.prescribed_at.desc())
            )
        ).all()
    )

    treatments = list(
        (
            await session.scalars(
                select(HospitalizationTreatment)
                .where(HospitalizationTreatment.hospitalization_id.in_(stay_ids))
                .order_by(HospitalizationTreatment.started_at.desc())
            )
        ).all()
    )
    # Las notas anuladas no se muestran fuera de la internación: acá se lee la historia.
    notes = list(
        (
            await session.scalars(
                select(HospitalizationNote)
                .where(
                    HospitalizationNote.hospitalization_id.in_(stay_ids),
                    HospitalizationNote.status == ClinicalNoteStatus.ACTIVE,
                )
                .order_by(HospitalizationNote.noted_at.desc())
            )
        ).all()
    )

    accounts = dict(
        (
            await session.execute(
                select(Account.id, Account.hospitalization_id).where(
                    Account.hospitalization_id.in_(stay_ids)
                )
            )
        ).all()
    )
    payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(Payment.account_id.in_(accounts.keys()))
                .order_by(Payment.paid_at.desc())
            )
        ).all()
        if accounts
        else []
    )
    # La plata del paciente: lo que está a su cargo y lo que efectivamente pagó.
    patient_charged = await session.scalar(
        select(func.coalesce(func.sum(ChargeItem.amount), 0)).where(
            ChargeItem.account_id.in_(accounts.keys() or [uuid.uuid4()]),
            ChargeItem.status == ChargeItemStatus.ACTIVE,
            ChargeItem.responsible_party == ResponsibleParty.PATIENT,
        )
    )
    paid = sum(
        (payment.amount for payment in payments if payment.status == PaymentStatus.CONFIRMED),
        Decimal(0),
    )

    return PatientRecord(
        patient=patient,
        coverages=coverages,
        hospitalizations=hospitalizations,
        locations=await _locations(session, stay_ids),
        diagnoses=diagnoses,
        practices=practices,
        prescriptions=prescriptions,
        treatments=treatments,
        notes=notes,
        payments=payments,
        payment_stays={
            payment.id: accounts[payment.account_id] for payment in payments
        },
        patient_charged=Decimal(patient_charged or 0),
        paid=paid,
    )


def performed_practices(record: PatientRecord) -> int:
    return sum(
        1
        for order, _, _ in record.practices
        if order.status == PracticeOrderStatus.PERFORMED
    )


def consultations(record: PatientRecord) -> int:
    return sum(1 for _, is_consultation, _ in record.practices if is_consultation)
