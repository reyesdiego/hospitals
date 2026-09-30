"""Schemas de la historia clínica del paciente: todo lo suyo, en un solo lugar."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.account import PaymentMethod, PaymentStatus
from app.models.admission import AdmissionType
from app.models.diagnosis import DiagnosisRole, DiagnosisStage
from app.models.hospitalization import HospitalizationStatus
from app.models.practice import PracticeOrderStatus
from app.models.prescription import PrescriptionKind
from app.models.treatment import (
    ClinicalNoteKind,
    MedicationRoute,
    TreatmentKind,
    TreatmentStatus,
)
from app.schemas.domain import PatientCoverageRead, PatientRead


class PatientStayRead(BaseModel):
    """Una internación del paciente, resumida para la línea de tiempo."""

    hospitalization_id: uuid.UUID
    status: HospitalizationStatus
    admission_type: AdmissionType | None
    admitted_at: datetime | None
    clinically_discharged_at: datetime | None
    administratively_discharged_at: datetime | None
    admission_reason: str
    facility_name: str | None
    service_name: str | None
    bed_label: str | None
    #: El diagnóstico que mejor explica la internación: el principal de egreso, y si
    #: todavía no lo tiene, el principal de ingreso.
    principal_diagnosis: str | None
    length_of_stay_days: int | None


class PatientDiagnosisRead(BaseModel):
    hospitalization_id: uuid.UUID
    code: str
    description: str
    role: DiagnosisRole
    stage: DiagnosisStage
    diagnosed_at: datetime
    diagnosed_by_name: str | None
    notes: str | None


class PatientPracticeRead(BaseModel):
    hospitalization_id: uuid.UUID
    code: str
    name: str
    status: PracticeOrderStatus
    quantity: Decimal
    prescribed_at: datetime
    performed_at: datetime | None
    #: Las consultas se separan del resto: son la otra forma de atención.
    is_consultation: bool
    amount: Decimal | None
    indication: str | None


class PatientPrescriptionRead(BaseModel):
    hospitalization_id: uuid.UUID
    kind: PrescriptionKind
    description: str
    presentation: str | None
    dosage: str | None
    duration_days: int | None
    instructions: str | None
    prescribed_at: datetime


class PatientTreatmentRead(BaseModel):
    hospitalization_id: uuid.UUID
    kind: TreatmentKind
    description: str
    presentation: str | None
    dose: str | None
    route: MedicationRoute | None
    frequency: str | None
    status: TreatmentStatus
    started_at: datetime
    ended_at: datetime | None
    end_reason: str | None


class PatientNoteRead(BaseModel):
    hospitalization_id: uuid.UUID
    kind: ClinicalNoteKind
    note: str
    noted_at: datetime
    recorded_by_user_name: str | None


class PatientPaymentRead(BaseModel):
    hospitalization_id: uuid.UUID
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    paid_at: datetime
    reference: str | None
    received_by: str | None


class PatientRecordTotals(BaseModel):
    stays: int
    open_stays: int
    performed_practices: int
    consultations: int
    #: Plata: lo que se le cargó al paciente, lo cobrado y lo que sigue debiendo.
    patient_charged: Decimal
    paid: Decimal
    balance: Decimal


class PatientRecordRead(BaseModel):
    patient: PatientRead
    age: int | None
    coverages: list[PatientCoverageRead]
    totals: PatientRecordTotals
    stays: list[PatientStayRead]
    diagnoses: list[PatientDiagnosisRead]
    practices: list[PatientPracticeRead]
    prescriptions: list[PatientPrescriptionRead]
    treatments: list[PatientTreatmentRead]
    notes: list[PatientNoteRead]
    payments: list[PatientPaymentRead]

    @staticmethod
    def age_from(birth_date: date | None, today: date) -> int | None:
        if not birth_date:
            return None
        years = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            years -= 1
        return max(years, 0)
