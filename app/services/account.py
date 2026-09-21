"""Hospitalization account and charges. Financial closure is a separate concern from
clinical discharge: closing the account never gates the clinical workflow."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DomainError
from app.core.users import STAFF, RequestUser
from app.models.account import (
    Account,
    AccountStatus,
    ChargeCategory,
    ChargeItem,
    ChargeItemStatus,
    Payment,
    PaymentStatus,
    ResponsibleParty,
)
from app.models.admission import Admission
from app.models.audit import HospitalizationEventType
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.practice import MedicalPractice
from app.schemas.workflow import (
    ChargeItemCreate,
    ChargeItemVoidCreate,
    PaymentCreate,
    PaymentVoidCreate,
)
from app.services.access import require_editable
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


def default_responsible_party(account: Account) -> ResponsibleParty:
    """Quién paga un cargo cuando nadie lo aclara.

    Con cobertura detrás el cargo se le factura al financiador; sin cobertura el paciente
    es particular y paga todo de su bolsillo.
    """

    return ResponsibleParty.PAYER if account.coverage_id else ResponsibleParty.PATIENT


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
    responsible_party: ResponsibleParty | None = None,
) -> ChargeItem:
    """Add a charge inside the caller's transaction; the caller owns the commit."""

    item = ChargeItem(
        account_id=account.id,
        practice_id=practice_id,
        practice_code=practice_code,
        category=category,
        responsible_party=responsible_party or default_responsible_party(account),
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


async def patient_balance_for_account(
    session: AsyncSession,
    account_id: uuid.UUID,
) -> tuple[Decimal, Decimal, Decimal]:
    """Cargado al paciente, cobrado y saldo, sin traer la cuenta entera.

    Es lo que mira el alta administrativa, que corre dentro de la transacción del alta.
    """

    charged = await session.scalar(
        select(func.coalesce(func.sum(ChargeItem.amount), 0)).where(
            ChargeItem.account_id == account_id,
            ChargeItem.status == ChargeItemStatus.ACTIVE,
            ChargeItem.responsible_party == ResponsibleParty.PATIENT,
        )
    )
    paid = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.account_id == account_id,
            Payment.status == PaymentStatus.CONFIRMED,
        )
    )
    charged, paid = Decimal(charged or 0), Decimal(paid or 0)
    return charged, paid, max(charged - paid, Decimal(0))


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
    def __init__(self, session: AsyncSession, user: RequestUser = STAFF):
        self.session = session
        self.user = user

    async def _editable(self, hospitalization_id: uuid.UUID, action: str) -> None:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if hospitalization:
            require_editable(self.session, hospitalization, self.user, action=action)

    async def for_hospitalization(self, hospitalization_id: uuid.UUID) -> Account:
        account = await self.session.scalar(
            select(Account)
            .options(selectinload(Account.charge_items), selectinload(Account.payments))
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
            await self._editable(hospitalization_id, "Agregar un cargo a la cuenta")
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
                responsible_party=payload.responsible_party,
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
            await self._editable(hospitalization_id, "Anular un cargo de la cuenta")
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

    async def register_payment(
        self,
        hospitalization_id: uuid.UUID,
        payload: PaymentCreate,
    ) -> Payment:
        """Cobrar al paciente lo que está a su cargo.

        No se le puede cobrar más de lo que debe: si el importe pasa el saldo, el cargo
        que falta hay que agregarlo a la cuenta primero.
        """

        async with self.session.begin():
            account = await require_open_account(self.session, hospitalization_id)
            _, _, balance = await patient_balance_for_account(self.session, account.id)
            if payload.amount > balance:
                raise DomainError(
                    f"El pago supera el saldo del paciente: adeuda {balance} "
                    f"{account.currency}",
                    409,
                )

            now = datetime.now(UTC)
            payment = Payment(
                account_id=account.id,
                amount=payload.amount,
                method=payload.method,
                status=PaymentStatus.CONFIRMED,
                paid_at=payload.paid_at or now,
                received_by=payload.received_by or self.user.name,
                reference=payload.reference,
                notes=payload.notes,
            )
            self.session.add(payment)
            record_event(
                self.session,
                HospitalizationEventType.PAYMENT_REGISTERED,
                hospitalization_id=hospitalization_id,
                patient_id=account.patient_id,
                actor=payment.received_by,
                occurred_at=now,
                details={
                    "amount": str(payload.amount),
                    "method": payload.method.value,
                    "reference": payload.reference,
                },
            )
            await self.session.flush()
            return payment

    async def void_payment(
        self,
        hospitalization_id: uuid.UUID,
        payment_id: uuid.UUID,
        payload: PaymentVoidCreate,
    ) -> Payment:
        """Anula un pago mal cargado; el importe vuelve a quedar adeudado."""

        async with self.session.begin():
            account = await require_open_account(self.session, hospitalization_id)
            payment = await self.session.get(Payment, payment_id)
            if not payment or payment.account_id != account.id:
                raise DomainError("Pago inexistente", 404)
            if payment.status == PaymentStatus.VOID:
                return payment

            now = datetime.now(UTC)
            payment.status = PaymentStatus.VOID
            payment.voided_at = now
            payment.voided_by = payload.actor or self.user.name
            payment.void_reason = payload.reason
            record_event(
                self.session,
                HospitalizationEventType.PAYMENT_VOIDED,
                hospitalization_id=hospitalization_id,
                patient_id=account.patient_id,
                actor=payment.voided_by,
                occurred_at=now,
                details={"amount": str(payment.amount), "reason": payload.reason},
            )
            await self.session.flush()
            return payment

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
    def patient_total(account: Account) -> Decimal:
        """Lo que se le cobra al paciente: copagos y todo lo que no cubre el financiador."""

        return sum(
            (
                item.amount
                for item in account.charge_items
                if item.status == ChargeItemStatus.ACTIVE
                and item.responsible_party == ResponsibleParty.PATIENT
            ),
            Decimal(0),
        )

    @staticmethod
    def payer_total(account: Account) -> Decimal:
        return AccountService.total(account) - AccountService.patient_total(account)

    @staticmethod
    def paid_total(account: Account) -> Decimal:
        """Lo cobrado: un pago anulado no cancela nada."""

        return sum(
            (
                payment.amount
                for payment in account.payments
                if payment.status == PaymentStatus.CONFIRMED
            ),
            Decimal(0),
        )

    @staticmethod
    def patient_balance(account: Account) -> Decimal:
        """Lo que el paciente todavía debe. Negativo no: un pago de más queda a favor."""

        return max(
            AccountService.patient_total(account) - AccountService.paid_total(account),
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
