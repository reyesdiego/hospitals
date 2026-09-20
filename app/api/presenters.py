"""Response builders shared by the routers."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.account import Account, ChargeItem
from app.models.bed import Bed, BedStatus
from app.models.practice import HealthPlanPractice, HospitalizationPractice
from app.models.room import Room
from app.schemas.domain import BedRead, PatientRead, RoomRead
from app.schemas.practice import (
    HealthPlanPracticeRead,
    HospitalizationPracticeRead,
    NursingTaskRead,
)
from app.schemas.workflow import AccountRead, ChargeItemRead
from app.services.account import AccountService
from app.services.nursing import NursingTask
from app.services.plan_coverage import effective_waiting_period
from app.services.room import occupancy_of


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


def health_plan_practice_read(entry: HealthPlanPractice) -> HealthPlanPracticeRead:
    """Flattens the practice into the row, so the cartilla reads without a second request."""

    practice = entry.practice
    return HealthPlanPracticeRead(
        id=entry.id,
        health_plan_id=entry.health_plan_id,
        practice_id=entry.practice_id,
        practice_code=practice.code,
        practice_name=practice.name,
        nomenclador=practice.nomenclador,
        chapter=practice.chapter,
        practice_type=practice.practice_type,
        practice_requires_authorization=practice.requires_authorization,
        practice_waiting_period_days=practice.default_waiting_period_days,
        is_covered=entry.is_covered,
        waiting_period_days=entry.waiting_period_days,
        effective_waiting_period_days=effective_waiting_period(entry, practice),
        copayment_amount=entry.copayment_amount,
        requires_authorization=entry.requires_authorization,
        notes=entry.notes,
        created_at=entry.created_at,
    )


def room_read(room: Room, bed_statuses: list[BedStatus]) -> RoomRead:
    """La habitación se lee con el estado que le dan sus camas, no con el que quedó escrito."""

    occupancy = occupancy_of(room, bed_statuses)
    return RoomRead(
        id=room.id,
        facility_id=room.facility_id,
        code=room.code,
        ward=room.ward,
        status=occupancy.status,
        administrative_status=room.status,
        beds=occupancy.beds,
        available_beds=occupancy.available,
        reserved_beds=occupancy.reserved,
        occupied_beds=occupancy.occupied,
        cleaning_beds=occupancy.cleaning,
        unavailable_beds=occupancy.unavailable,
        created_at=room.created_at,
    )


def nursing_task_read(task: NursingTask) -> NursingTaskRead:
    order, patient = task.order, task.patient
    prescriber = task.prescribed_by
    return NursingTaskRead(
        id=order.id,
        hospitalization_id=order.hospitalization_id,
        practice_id=order.practice_id,
        practice_code=order.practice_code,
        practice_name=order.practice_name,
        status=order.status,
        quantity=order.quantity,
        patient_id=patient.id,
        patient_name=f"{patient.last_name}, {patient.first_name}",
        ward=task.ward,
        room_code=task.room_code,
        bed_code=task.bed_code,
        prescribed_by=(
            f"{prescriber.last_name}, {prescriber.first_name}" if prescriber else None
        ),
        prescribed_at=order.prescribed_at,
        performed_at=order.performed_at,
        performed_by=order.performed_by_user_name,
        cancelled_at=order.cancelled_at,
        indication=order.indication,
        notes=order.notes,
    )
