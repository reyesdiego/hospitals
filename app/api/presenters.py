"""Response builders shared by the routers."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.account import Account, ChargeItem
from app.models.bed import Bed
from app.models.practice import HospitalizationPractice
from app.models.room import Room
from app.schemas.domain import BedRead, PatientRead
from app.schemas.practice import HospitalizationPracticeRead
from app.schemas.workflow import AccountRead, ChargeItemRead
from app.services.account import AccountService


async def bed_read(
    session: AsyncSession,
    bed: Bed,
    room: Room | None = None,
    patient: PatientRead | None = None,
    reserved_for: PatientRead | None = None,
    reservation_expires_at: datetime | None = None,
) -> BedRead:
    room = room or await session.get(Room, bed.room_id)
    if not room:
        raise DomainError("La cama no tiene una habitación válida", 500)
    return BedRead(
        id=bed.id,
        facility_id=bed.facility_id,
        room_id=bed.room_id,
        code=bed.code,
        ward=bed.ward,
        room=room.code,
        status=bed.status,
        patient=patient,
        reserved_for=reserved_for,
        reservation_expires_at=reservation_expires_at,
    )


def account_read(account: Account) -> AccountRead:
    return AccountRead(
        id=account.id,
        hospitalization_id=account.hospitalization_id,
        patient_id=account.patient_id,
        coverage_id=account.coverage_id,
        status=account.status,
        currency=account.currency,
        opened_at=account.opened_at,
        ready_for_review_at=account.ready_for_review_at,
        closed_at=account.closed_at,
        total_amount=AccountService.total(account),
        voided_amount=AccountService.voided_total(account),
        charge_items=[
            ChargeItemRead.model_validate(item)
            for item in sorted(account.charge_items, key=lambda item: item.charged_at)
        ],
    )


async def hospitalization_practice_read(
    session: AsyncSession,
    order: HospitalizationPractice,
) -> HospitalizationPracticeRead:
    """The practice carries the charge it generated, so the clinical record and the
    account are read together."""

    charge = None
    if order.charge_item_id:
        item = await session.get(ChargeItem, order.charge_item_id)
        charge = ChargeItemRead.model_validate(item) if item else None
    return HospitalizationPracticeRead.model_validate(order).model_copy(
        update={"charge": charge}
    )
