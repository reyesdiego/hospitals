"""Unit checks of the bed occupancy rules that do not need a database."""

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
from app.models.bed import Bed, BedAssignment, BedStatus, BedStatusHistory
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.services.bed_assignment import BedAssignmentService


class FakeSession:
    def __init__(self):
        self.added = []
        self.flushed = False

    async def get(self, *_args, **_kwargs):
        return None

    async def scalar(self, _):
        return None

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


def build_bed(status: BedStatus = BedStatus.AVAILABLE, code: str = "101-A") -> Bed:
    return Bed(
        id=uuid.uuid4(),
        facility_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        ward="A",
        code=code,
        status=status,
    )


def build_hospitalization(status=HospitalizationStatus.PENDING_BED) -> Hospitalization:
    return Hospitalization(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        status=status,
        admission_reason="Observation",
    )


def test_assign_available_bed_occupies_it_and_starts_the_hospitalization():
    session = FakeSession()
    service = BedAssignmentService(session)
    hospitalization = build_hospitalization()
    bed = build_bed()
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

    history = [item for item in session.added if isinstance(item, BedStatusHistory)]
    assert assignment in session.added
    assert assignment.hospitalization_id == hospitalization.id
    assert assignment.bed_id == bed.id
    assert assignment.ended_at is None
    assert bed.status == BedStatus.OCCUPIED
    assert [entry.new_status for entry in history] == [BedStatus.OCCUPIED]
    assert hospitalization.status == HospitalizationStatus.IN_PROGRESS
    assert hospitalization.admitted_at is not None
    assert hospitalization.facility_id == bed.facility_id
    assert admission.status == AdmissionStatus.ADMITTED
    assert admission.admitted_at == hospitalization.admitted_at
    assert session.flushed is True


def test_assign_rejects_unavailable_bed():
    session = FakeSession()
    service = BedAssignmentService(session)
    hospitalization = build_hospitalization()
    bed = build_bed(BedStatus.BLOCKED)
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    session.get = AsyncMock(return_value=bed)

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.assign(hospitalization.id, bed.id, commit=False))

    assert exc_info.value.status_code == 409
    assert session.added == []


def test_assign_rejects_a_bed_reserved_for_another_hospitalization():
    session = FakeSession()
    service = BedAssignmentService(session)
    hospitalization = build_hospitalization()
    bed = build_bed(BedStatus.RESERVED)
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    session.get = AsyncMock(return_value=bed)
    service._reservation_to_complete = AsyncMock(
        side_effect=DomainError("La cama está reservada para otra internación", 409)
    )

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.assign(hospitalization.id, bed.id, commit=False))

    assert exc_info.value.status_code == 409
    assert session.added == []


def test_transfer_success_preserves_history_and_updates_bed_states():
    session = FakeTransactionalSession()
    service = BedAssignmentService(session)
    hospitalization = build_hospitalization(HospitalizationStatus.IN_PROGRESS)
    source_bed = build_bed(BedStatus.OCCUPIED)
    destination_bed = build_bed(BedStatus.AVAILABLE, code="201-A")
    current_assignment = BedAssignment(
        id=uuid.uuid4(),
        hospitalization_id=hospitalization.id,
        bed_id=source_bed.id,
        started_at=datetime.now(UTC),
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=current_assignment)
    service._active_assignment_for_bed = AsyncMock(return_value=None)
    service._lock_beds = AsyncMock(
        return_value={source_bed.id: source_bed, destination_bed.id: destination_bed}
    )

    transfer = asyncio.run(
        service.transfer(hospitalization.id, destination_bed.id, reason="ICU", completed_by="nurse")
    )

    new_assignment = next(obj for obj in session.added if isinstance(obj, BedAssignment))
    assert transfer.from_bed_id == source_bed.id
    assert transfer.to_bed_id == destination_bed.id
    assert current_assignment.ended_at is not None
    assert current_assignment.ended_by == "nurse"
    assert source_bed.status == BedStatus.PENDING_CLEANING
    assert destination_bed.status == BedStatus.OCCUPIED
    assert new_assignment.hospitalization_id == hospitalization.id
    assert new_assignment.bed_id == destination_bed.id
    assert new_assignment.ended_at is None


def test_transfer_rejects_same_bed():
    session = FakeTransactionalSession()
    service = BedAssignmentService(session)
    hospitalization = build_hospitalization(HospitalizationStatus.IN_PROGRESS)
    bed_id = uuid.uuid4()
    current_assignment = BedAssignment(
        hospitalization_id=hospitalization.id,
        bed_id=bed_id,
        started_at=datetime.now(UTC),
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=current_assignment)

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.transfer(hospitalization.id, bed_id))

    assert exc_info.value.status_code == 409
    assert current_assignment.ended_at is None


def test_failed_transfer_to_occupied_destination_leaves_original_assignment_unchanged():
    session = FakeTransactionalSession()
    service = BedAssignmentService(session)
    hospitalization = build_hospitalization(HospitalizationStatus.IN_PROGRESS)
    source_bed = build_bed(BedStatus.OCCUPIED)
    destination_bed = build_bed(BedStatus.OCCUPIED, code="201-A")
    current_assignment = BedAssignment(
        hospitalization_id=hospitalization.id,
        bed_id=source_bed.id,
        started_at=datetime.now(UTC),
    )
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=current_assignment)
    service._lock_beds = AsyncMock(
        return_value={source_bed.id: source_bed, destination_bed.id: destination_bed}
    )

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.transfer(hospitalization.id, destination_bed.id))

    assert exc_info.value.status_code == 409
    assert current_assignment.ended_at is None
    assert source_bed.status == BedStatus.OCCUPIED
    assert destination_bed.status == BedStatus.OCCUPIED
    assert session.added == []


def test_transfer_requires_an_active_bed():
    session = FakeTransactionalSession()
    service = BedAssignmentService(session)
    hospitalization = build_hospitalization(HospitalizationStatus.IN_PROGRESS)
    service._hospitalization_for_update = AsyncMock(return_value=hospitalization)
    service._active_assignment_for_hospitalization = AsyncMock(return_value=None)

    with pytest.raises(DomainError) as exc_info:
        asyncio.run(service.transfer(hospitalization.id, uuid.uuid4()))

    assert exc_info.value.status_code == 404
