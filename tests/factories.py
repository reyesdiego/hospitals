"""Minimal fixtures shared by the integration tests."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admission import Admission, AdmissionOrigin, AdmissionType, AuthorizationStatus
from app.models.bed import Bed, BedStatus
from app.models.facility import Facility
from app.models.patient import Patient
from app.models.professional import Professional
from app.models.room import Room
from app.models.service import Service
from app.schemas.domain import AdmissionCreate
from app.services.admission import AdmissionWorkflowService


@dataclass
class Scenario:
    facility_id: uuid.UUID
    room_id: uuid.UUID
    patient_id: uuid.UUID
    other_patient_id: uuid.UUID
    service_id: uuid.UUID
    other_service_id: uuid.UUID
    practitioner_id: uuid.UUID
    bed_ids: list[uuid.UUID]


async def build_scenario(session: AsyncSession, beds: int = 2) -> Scenario:
    facility = Facility(name="Hospital Central", code=f"HC-{uuid.uuid4().hex[:6]}")
    session.add(facility)
    await session.flush()

    room = Room(facility_id=facility.id, code="101", ward="Clínica Médica")
    session.add(room)
    await session.flush()

    bed_rows = [
        Bed(
            facility_id=facility.id,
            room_id=room.id,
            code=f"101-{index}",
            ward=room.ward,
            status=BedStatus.AVAILABLE,
        )
        for index in range(beds)
    ]
    patient = Patient(
        first_name="Ana",
        last_name="Gomez",
        document_type="DNI",
        document_number=uuid.uuid4().hex[:10],
        birth_date=date(1980, 5, 4),
    )
    other_patient = Patient(
        first_name="Luis",
        last_name="Perez",
        document_type="DNI",
        document_number=uuid.uuid4().hex[:10],
    )
    service = Service(name="Clínica Médica", code=f"CM-{uuid.uuid4().hex[:6]}")
    other_service = Service(name="Terapia Intensiva", code=f"TI-{uuid.uuid4().hex[:6]}")
    practitioner = Professional(
        first_name="Marta",
        last_name="Diaz",
        document_type="DNI",
        document_number=uuid.uuid4().hex[:10],
    )
    session.add_all([*bed_rows, patient, other_patient, service, other_service, practitioner])
    await session.commit()

    return Scenario(
        facility_id=facility.id,
        room_id=room.id,
        patient_id=patient.id,
        other_patient_id=other_patient.id,
        service_id=service.id,
        other_service_id=other_service.id,
        practitioner_id=practitioner.id,
        bed_ids=[bed.id for bed in bed_rows],
    )


def admission_payload(scenario: Scenario, **overrides) -> AdmissionCreate:
    """Admission request payload: the entry point of the whole flow."""

    data: dict = {
        "patient_id": scenario.patient_id,
        "origin": AdmissionOrigin.EMERGENCY_ROOM,
        "admission_type": AdmissionType.EMERGENCY,
        "facility_id": scenario.facility_id,
        "identity_validated": True,
        "duplicate_checked": True,
        "authorization_status": AuthorizationStatus.NOT_REQUIRED,
        "responsible_contact_name": "Juan Gomez",
        "responsible_contact_phone": "11-5555-5555",
        "admission_reason": "Dolor abdominal agudo",
        "responsible_physician": "Marta Diaz",
        "responsible_physician_id": scenario.practitioner_id,
        "requesting_service_id": scenario.service_id,
        "confirm_admission": False,
    }
    data.update(overrides)
    return AdmissionCreate(**data)


async def request_admission(
    session: AsyncSession,
    scenario: Scenario,
    **overrides,
) -> Admission:
    return await AdmissionWorkflowService(session).create(admission_payload(scenario, **overrides))


async def hospitalization_from_admission(
    session: AsyncSession,
    scenario: Scenario,
    **overrides,
) -> uuid.UUID:
    """Hospitalization id of a fresh admission request."""

    admission = await request_admission(session, scenario, **overrides)
    assert admission.hospitalization_id is not None
    return admission.hospitalization_id
