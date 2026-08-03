import asyncio
import uuid

from app.models.bed import BedStatus
from app.services.bed_assignment import BedAssignmentService


class FakeAssignment:
    status = None
    hospitalization_id = uuid.uuid4()


class FakeSession:
    async def scalar(self, _):
        return FakeAssignment()


def test_current_status_infers_occupied_for_legacy_active_assignment():
    status = asyncio.run(BedAssignmentService(FakeSession()).current_status(uuid.uuid4()))

    assert status == BedStatus.OCCUPIED
