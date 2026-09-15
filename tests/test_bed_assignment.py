import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import DomainError
from app.models.admission import (
    Admission,
    AdmissionOrigin,
    AdmissionStatus,
    AdmissionType,
    AuthorizationStatus,
)
from app.models.bed import Bed, BedAssignment, BedStatus
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.services.bed_assignment import BedAssignmentService


class FakeAssignment:
    status = None
    hospitalization_id = uuid.uuid4()


class FakeSession:
    def __init__(self):
        self.added = []
        self.flushed = False

    async def get(self, *_args, **_kwargs):
        return None

    async def scalar(self, _):
        return FakeAssignment()

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objects):
        self.added.extend(objects)

    async def flush(self):
        self.flushed = True


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class FakeTransactionalSession(FakeSession):
    def begin(self):
        return FakeTransaction()

    async def rollback(self):
        return None


def test_current_status_infers_occupied_for_legacy_active_assignment():
    status = asyncio.run(BedAssignmentService(FakeSession()).current_status(uuid.uuid4()))

    assert status == BedStatus.OCCUPIED


def test_assign_available_bed_successfully():
    session = FakeSession()
    service = BedAssignmentService(session)
    hospitalization = Hospitalization(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        status=HospitalizationStatus.PENDING_BED,
        admission_reason="Observation",
    )
    bed = Bed(
        id=uuid.uuid4(),
        facility_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        ward="A",
        code="101-A",
        status=BedStatus.AVAILABLE,
    )
    admission = Admission(
        id=uuid.uuid4(),
        patient_id=hospitalization.patient_id,
        hospitalization_id=hospitalization.id,
        origin=AdmissionOrigin.EMERGENCY_ROOM,
        admission_type=AdmissionType.EMERGENCY,
        status=AdmissionStatus.PENDING_BED,
        identity_validated=True,
        duplicate_checked=True,
        authorization_status=AuthorizationStatus.NOT_REQUIRED,
        responsible_contact_name="Contact",
        responsible_contact_phone="555",
        admission_reason="Observation",
        responsible_physician="Doctor",
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=None)
    service._active_assignment_for_bed = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=bed)
    session.scalar = AsyncMock(return_value=admission)

    assignment = asyncio.run(service.assign(hospitalization.id, bed.id, commit=False))

    assert assignment in session.added
    assert assignment.hospitalization_id == hospitalization.id
    assert assignment.bed_id == bed.id
    assert assignment.status == BedStatus.OCCUPIED
    assert bed.status == BedStatus.OCCUPIED
    assert hospitalization.status == HospitalizationStatus.IN_PROGRESS
    assert hospitalization.admitted_at is not None
    assert admission.status == AdmissionStatus.ADMITTED
    assert admission.admitted_at == hospitalization.admitted_at
    assert session.flushed is True


def test_assign_rejects_unavailable_bed():
    session = FakeSession()
    service = BedAssignmentService(session)
    hospitalization = Hospitalization(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        status=HospitalizationStatus.PENDING_BED,
        admission_reason="Observation",
    )
    bed = Bed(
        id=uuid.uuid4(),
        facility_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        ward="A",
        code="101-A",
        status=BedStatus.BLOCKED,
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    session.get = AsyncMock(return_value=bed)

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.assign(hospitalization.id, bed.id, commit=False))

    assert exc_info.value.status_code == 409
    assert session.added == []


def test_transfer_success_preserves_history_and_updates_bed_states():
    session = FakeTransactionalSession()
    service = BedAssignmentService(session)
    hospitalization_id = uuid.uuid4()
    source_bed = Bed(
        id=uuid.uuid4(),
        facility_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        ward="A",
        code="101-A",
        status=BedStatus.OCCUPIED,
    )
    destination_bed = Bed(
        id=uuid.uuid4(),
        facility_id=source_bed.facility_id,
        room_id=uuid.uuid4(),
        ward="B",
        code="201-A",
        status=BedStatus.AVAILABLE,
    )
    hospitalization = Hospitalization(
        id=hospitalization_id,
        patient_id=uuid.uuid4(),
        status=HospitalizationStatus.IN_PROGRESS,
        admission_reason="Observation",
    )
    current_assignment = BedAssignment(
        id=uuid.uuid4(),
        hospitalization_id=hospitalization_id,
        bed_id=source_bed.id,
        status=BedStatus.OCCUPIED,
        started_at=datetime.now(UTC),
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=current_assignment)
    service._lock_beds = AsyncMock(return_value={source_bed.id: source_bed, destination_bed.id: destination_bed})

    transfer = asyncio.run(
        service.transfer(hospitalization_id, destination_bed.id, reason="ICU", completed_by="nurse")
    )

    new_assignment = next(obj for obj in session.added if isinstance(obj, BedAssignment))
    assert transfer.from_bed_id == source_bed.id
    assert transfer.to_bed_id == destination_bed.id
    assert current_assignment.ended_at is not None
    assert current_assignment.ended_by == "nurse"
    assert source_bed.status == BedStatus.PENDING_CLEANING
    assert destination_bed.status == BedStatus.OCCUPIED
    assert new_assignment.hospitalization_id == hospitalization_id
    assert new_assignment.bed_id == destination_bed.id
    assert new_assignment.ended_at is None


def test_transfer_rejects_same_bed():
    session = FakeTransactionalSession()
    service = BedAssignmentService(session)
    hospitalization_id = uuid.uuid4()
    bed_id = uuid.uuid4()
    hospitalization = Hospitalization(
        id=hospitalization_id,
        patient_id=uuid.uuid4(),
        status=HospitalizationStatus.IN_PROGRESS,
        admission_reason="Observation",
    )
    current_assignment = BedAssignment(
        hospitalization_id=hospitalization_id,
        bed_id=bed_id,
        status=BedStatus.OCCUPIED,
        started_at=datetime.now(UTC),
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=current_assignment)

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.transfer(hospitalization_id, bed_id))

    assert exc_info.value.status_code == 409
    assert current_assignment.ended_at is None


def test_failed_transfer_to_occupied_destination_leaves_original_assignment_unchanged():
    session = FakeTransactionalSession()
    service = BedAssignmentService(session)
    hospitalization_id = uuid.uuid4()
    source_bed = Bed(
        id=uuid.uuid4(),
        facility_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        ward="A",
        code="101-A",
        status=BedStatus.OCCUPIED,
    )
    destination_bed = Bed(
        id=uuid.uuid4(),
        facility_id=source_bed.facility_id,
        room_id=uuid.uuid4(),
        ward="B",
        code="201-A",
        status=BedStatus.OCCUPIED,
    )
    hospitalization = Hospitalization(
        id=hospitalization_id,
        patient_id=uuid.uuid4(),
        status=HospitalizationStatus.IN_PROGRESS,
        admission_reason="Observation",
    )
    current_assignment = BedAssignment(
        hospitalization_id=hospitalization_id,
        bed_id=source_bed.id,
        status=BedStatus.OCCUPIED,
        started_at=datetime.now(UTC),
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=current_assignment)
    service._lock_beds = AsyncMock(return_value={source_bed.id: source_bed, destination_bed.id: destination_bed})

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.transfer(hospitalization_id, destination_bed.id))

    assert exc_info.value.status_code == 409
    assert current_assignment.ended_at is None
    assert source_bed.status == BedStatus.OCCUPIED
    assert destination_bed.status == BedStatus.OCCUPIED
    assert session.added == []
