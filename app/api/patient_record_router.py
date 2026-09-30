"""Historia clínica del paciente: la vista por paciente de todo lo que se le hizo."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.schemas.domain import PatientCoverageRead, PatientRead
from app.schemas.patient_record import (
    PatientDiagnosisRead,
    PatientNoteRead,
    PatientPaymentRead,
    PatientPracticeRead,
    PatientPrescriptionRead,
    PatientRecordRead,
    PatientRecordTotals,
    PatientStayRead,
    PatientTreatmentRead,
)
from app.services.patient_record import (
    build_record,
    consultations,
    length_of_stay_days,
    performed_practices,
)

router = APIRouter(tags=["patient-record"])


@router.get("/patients/{patient_id}/record", response_model=PatientRecordRead)
async def get_patient_record(patient_id: uuid.UUID, session: DbSession):
    """Todo lo del paciente en una sola respuesta: internaciones, diagnósticos,
    prácticas y consultas, medicación indicada al alta y pagos."""

    record = await build_record(session, patient_id)
    return PatientRecordRead(
        patient=PatientRead.model_validate(record.patient),
        age=PatientRecordRead.age_from(
            record.patient.birth_date,
            datetime.now(UTC).date(),
        ),
        coverages=[PatientCoverageRead.model_validate(item) for item in record.coverages],
        totals=PatientRecordTotals(
            stays=len(record.hospitalizations),
            open_stays=record.open_stays,
            performed_practices=performed_practices(record),
            consultations=consultations(record),
            patient_charged=record.patient_charged,
            paid=record.paid,
            balance=record.balance,
        ),
        stays=[
            PatientStayRead(
                hospitalization_id=stay.id,
                status=stay.status,
                admission_type=stay.admission_type,
                admitted_at=stay.admitted_at,
                clinically_discharged_at=stay.clinically_discharged_at,
                administratively_discharged_at=stay.administratively_discharged_at,
                admission_reason=stay.admission_reason,
                facility_name=record.locations[stay.id].facility_name,
                service_name=record.locations[stay.id].service_name,
                bed_label=record.locations[stay.id].bed_label,
                principal_diagnosis=record.principal_diagnosis(stay.id),
                length_of_stay_days=length_of_stay_days(stay),
            )
            for stay in record.hospitalizations
        ],
        diagnoses=[
            PatientDiagnosisRead(
                hospitalization_id=entry.hospitalization_id,
                code=entry.code,
                description=entry.description,
                role=entry.role,
                stage=entry.stage,
                diagnosed_at=entry.diagnosed_at,
                diagnosed_by_name=entry.diagnosed_by_name,
                notes=entry.notes,
            )
            for entry in record.diagnoses
        ],
        practices=[
            PatientPracticeRead(
                hospitalization_id=order.hospitalization_id,
                code=order.practice_code,
                name=order.practice_name,
                status=order.status,
                quantity=order.quantity,
                prescribed_at=order.prescribed_at,
                performed_at=order.performed_at,
                is_consultation=is_consultation,
                amount=amount,
                indication=order.indication,
            )
            for order, is_consultation, amount in record.practices
        ],
        prescriptions=[
            PatientPrescriptionRead(
                hospitalization_id=item.hospitalization_id,
                kind=item.kind,
                description=item.description,
                presentation=item.presentation,
                dosage=item.dosage,
                duration_days=item.duration_days,
                instructions=item.instructions,
                prescribed_at=item.prescribed_at,
            )
            for item in record.prescriptions
        ],
        treatments=[
            PatientTreatmentRead(
                hospitalization_id=item.hospitalization_id,
                kind=item.kind,
                description=item.description,
                presentation=item.presentation,
                dose=item.dose,
                route=item.route,
                frequency=item.frequency,
                status=item.status,
                started_at=item.started_at,
                ended_at=item.ended_at,
                end_reason=item.end_reason,
            )
            for item in record.treatments
        ],
        notes=[
            PatientNoteRead(
                hospitalization_id=item.hospitalization_id,
                kind=item.kind,
                note=item.note,
                noted_at=item.noted_at,
                recorded_by_user_name=item.recorded_by_user_name,
            )
            for item in record.notes
        ],
        payments=[
            PatientPaymentRead(
                hospitalization_id=record.payment_stays[payment.id],
                amount=payment.amount,
                method=payment.method,
                status=payment.status,
                paid_at=payment.paid_at,
                reference=payment.reference,
                received_by=payment.received_by,
            )
            for payment in record.payments
        ],
    )
