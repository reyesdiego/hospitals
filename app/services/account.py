"""Hospitalization account and charges. Financial closure is a separate concern from
clinical discharge: closing the account never gates the clinical workflow."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DomainError
from app.models.account import (
    Account,
    AccountStatus,
    ChargeCategory,
    ChargeItem,
    ChargeItemStatus,
)
from app.models.admission import Admission
from app.models.audit import HospitalizationEventType
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.practice import MedicalPractice
from app.schemas.workflow import ChargeItemCreate, ChargeItemVoidCreate
from app.services.audit import record_event


def open_account(
    session: AsyncSession,
    hospitalization: Hospitalization,
    *,
    coverage_id: uuid.UUID | None = None,
    at: datetime | None = None,
) -> Account:
    """Create the account of a hospitalization inside the caller's transaction."""

    account = Account(
        hospitalization_id=hospitalization.id,
        patient_id=hospitalization.patient_id,
        coverage_id=coverage_id,
        status=AccountStatus.OPEN,
        opened_at=at or datetime.now(UTC),
    )
    session.add(account)
    return account


async def require_open_account(session: AsyncSession, hospitalization_id: uuid.UUID) -> Account:
    """Lock the account of a hospitalization to add charges to it."""

    account = await session.scalar(
        select(Account).where(Account.hospitalization_id == hospitalization_id).with_for_update()
    )
    if not account:
        raise DomainError("La internación no tiene cuenta asociada", 404)
    if account.status in {AccountStatus.CLOSED, AccountStatus.CANCELLED}:
        raise DomainError("La cuenta está cerrada", 409)
    return account


def add_charge(
    session: AsyncSession,
    account: Account,
    *,
    category: ChargeCategory,
    description: str,
    quantity: Decimal,
    unit_price: Decimal,
    charged_at: datetime | None = None,
    recorded_by: str | None = None,
    notes: str | None = None,
    practice_id: uuid.UUID | None = None,
    practice_code: str | None = None,
) -> ChargeItem:
    """Add a charge inside the caller's transaction; the caller owns the commit."""

    item = ChargeItem(
        account_id=account.id,
        practice_id=practice_id,
        practice_code=practice_code,
        category=category,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        amount=(quantity * unit_price).quantize(Decimal("0.01")),
        charged_at=charged_at or datetime.now(UTC),
        recorded_by=recorded_by,
        notes=notes,
    )
    session.add(item)
    return item


def mark_ready_for_review(
    session: AsyncSession,
    account: Account,
    *,
    at: datetime,
    actor: str | None = None,
) -> None:
    if account.status != AccountStatus.OPEN:
        return
    account.status = AccountStatus.READY_FOR_REVIEW
    account.ready_for_review_at = at
    record_event(
        session,
        HospitalizationEventType.ACCOUNT_READY_FOR_REVIEW,
        hospitalization_id=account.hospitalization_id,
        patient_id=account.patient_id,
        actor=actor,
        occurred_at=at,
        details={"account_id": str(account.id)},
    )


class AccountService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def for_hospitalization(self, hospitalization_id: uuid.UUID) -> Account:
        account = await self.session.scalar(
            select(Account)
            .options(selectinload(Account.charge_items))
            .where(Account.hospitalization_id == hospitalization_id)
        )
        if not account:
            raise DomainError("La internación no tiene cuenta asociada", 404)
        return account

    async def add_charge_item(
        self,
        hospitalization_id: uuid.UUID,
        payload: ChargeItemCreate,
    ) -> ChargeItem:
        async with self.session.begin():
            account = await require_open_account(self.session, hospitalization_id)
            practice: MedicalPractice | None = None
            if payload.practice_id:
                practice = await self.session.get(MedicalPractice, payload.practice_id)
                if not practice:
                    raise DomainError("Práctica inexistente", 404)

            item = add_charge(
                self.session,
                account,
                category=payload.category,
                description=payload.description,
                quantity=payload.quantity,
                unit_price=payload.unit_price,
                charged_at=payload.charged_at,
                recorded_by=payload.recorded_by,
                notes=payload.notes,
                practice_id=practice.id if practice else None,
                practice_code=practice.code if practice else None,
            )
            await self.session.flush()
            return item

    async def void_charge_item(
        self,
        hospitalization_id: uuid.UUID,
        charge_item_id: uuid.UUID,
        payload: ChargeItemVoidCreate,
    ) -> ChargeItem:
        """Void a charge of the account. The line is kept and stops adding to the total."""

        async with self.session.begin():
            account = await require_open_account(self.session, hospitalization_id)
            item = await self.session.get(ChargeItem, charge_item_id)
            if not item or item.account_id != account.id:
                raise DomainError("Cargo inexistente", 404)
            if item.status == ChargeItemStatus.VOID:
                return item

            now = datetime.now(UTC)
            item.status = ChargeItemStatus.VOID
            item.voided_at = now
            item.voided_by = payload.actor
            item.void_reason = payload.reason
            record_event(
                self.session,
                HospitalizationEventType.CHARGE_ITEM_VOIDED,
                hospitalization_id=hospitalization_id,
                patient_id=account.patient_id,
                actor=payload.actor,
                occurred_at=now,
                details={
                    "charge_item_id": str(item.id),
                    "amount": str(item.amount),
                    "practice_code": item.practice_code,
                    "reason": payload.reason,
                },
            )
            await self.session.flush()
            return item

    async def close(self, account_id: uuid.UUID, *, actor: str | None = None) -> Account:
        """Financial closure: closes the account and only then the hospitalization."""

        async with self.session.begin():
            account = await self.session.get(Account, account_id, with_for_update=True)
            if not account:
                raise DomainError("Cuenta inexistente", 404)
            if account.status == AccountStatus.CLOSED:
                return account
            if account.status != AccountStatus.READY_FOR_REVIEW:
                raise DomainError("La cuenta no está lista para revisión", 409)

            now = datetime.now(UTC)
            account.status = AccountStatus.CLOSED
            account.closed_at = now

            hospitalization = await self.session.get(
                Hospitalization,
                account.hospitalization_id,
                with_for_update=True,
            )
            if hospitalization and hospitalization.status != HospitalizationStatus.CLOSED:
                hospitalization.status = HospitalizationStatus.CLOSED
                hospitalization.closed_at = now
                record_event(
                    self.session,
                    HospitalizationEventType.HOSPITALIZATION_CLOSED,
                    hospitalization_id=hospitalization.id,
                    patient_id=hospitalization.patient_id,
                    actor=actor,
                    occurred_at=now,
                    details={"account_id": str(account.id)},
                )
            return account

    @staticmethod
    def total(account: Account) -> Decimal:
        """Only the active charges: a voided charge is history, not money."""

        return sum(
            (
                item.amount
                for item in account.charge_items
                if item.status == ChargeItemStatus.ACTIVE
            ),
            Decimal(0),
        )

    @staticmethod
    def voided_total(account: Account) -> Decimal:
        return sum(
            (item.amount for item in account.charge_items if item.status == ChargeItemStatus.VOID),
            Decimal(0),
        )

    async def coverage_id_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
    ) -> uuid.UUID | None:
        return await self.session.scalar(
            select(Admission.coverage_id)
            .where(Admission.hospitalization_id == hospitalization_id)
            .order_by(Admission.created_at)
            .limit(1)
        )
