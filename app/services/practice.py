"""Medical practice catalog (nomenclador) and the tariffs agreed with each payer."""

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DomainError, integrity_conflict
from app.models.account import ChargeCategory, ChargeItem, ChargeItemStatus
from app.models.audit import HospitalizationEventType
from app.models.coverage import HealthPlan, PatientCoverage, Payer
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.practice import (
    HospitalizationPractice,
    MedicalPractice,
    MedicalPracticeTariff,
    Nomenclador,
    PracticeChapter,
    PracticeOrderStatus,
    PracticeSetting,
    PracticeType,
)
from app.models.professional import Professional
from app.models.service import Service
from app.schemas.practice import (
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticeCreate,
    HospitalizationPracticePerformCreate,
    MedicalPracticeCreate,
    MedicalPracticeTariffCreate,
    MedicalPracticeTariffUpdate,
    MedicalPracticeUpdate,
)
from app.services.account import add_charge, require_open_account
from app.services.audit import record_event

CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


class MedicalPracticeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_practices(
        self,
        *,
        nomenclador: Nomenclador | None = None,
        chapter: PracticeChapter | None = None,
        practice_type: PracticeType | None = None,
        setting: PracticeSetting | None = None,
        search: str | None = None,
        only_active: bool = False,
    ) -> list[MedicalPractice]:
        stmt = select(MedicalPractice).order_by(
            MedicalPractice.nomenclador, MedicalPractice.code
        )
        if nomenclador:
            stmt = stmt.where(MedicalPractice.nomenclador == nomenclador)
        if chapter:
            stmt = stmt.where(MedicalPractice.chapter == chapter)
        if practice_type:
            stmt = stmt.where(MedicalPractice.practice_type == practice_type)
        if setting:
            # A practice valid for both settings also answers a search by one of them.
            stmt = stmt.where(
                MedicalPractice.setting.in_([setting, PracticeSetting.AMBOS])
            )
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    MedicalPractice.code.ilike(pattern),
                    MedicalPractice.name.ilike(pattern),
                )
            )
        if only_active:
            stmt = stmt.where(MedicalPractice.is_active.is_(True))
        return list((await self.session.scalars(stmt)).all())

    async def get(self, practice_id: uuid.UUID) -> MedicalPractice:
        practice = await self.session.get(MedicalPractice, practice_id)
        if not practice:
            raise DomainError("Práctica inexistente", 404)
        return practice

    async def create(self, payload: MedicalPracticeCreate) -> MedicalPractice:
        self._validate_period(payload.valid_from, payload.valid_until)
        async with (
            integrity_conflict(self.session, "Código de práctica duplicado en el nomenclador"),
            self.session.begin(),
        ):
            practice = MedicalPractice(**payload.model_dump())
            self.session.add(practice)
            await self.session.flush()
            return practice

    async def update(
        self,
        practice_id: uuid.UUID,
        payload: MedicalPracticeUpdate,
    ) -> MedicalPractice:
        self._validate_period(payload.valid_from, payload.valid_until)
        async with (
            integrity_conflict(self.session, "Código de práctica duplicado en el nomenclador"),
            self.session.begin(),
        ):
            practice = await self.get(practice_id)
            for field, value in payload.model_dump().items():
                setattr(practice, field, value)
            await self.session.flush()
            return practice

    async def delete(self, practice_id: uuid.UUID) -> None:
        async with (
            integrity_conflict(
                self.session,
                "No se puede eliminar una práctica con registros asociados",
            ),
            self.session.begin(),
        ):
            practice = await self.get(practice_id)
            await self.session.delete(practice)

    async def list_tariffs(
        self,
        practice_id: uuid.UUID,
        *,
        payer_id: uuid.UUID | None = None,
    ) -> list[MedicalPracticeTariff]:
        await self.get(practice_id)
        stmt = (
            select(MedicalPracticeTariff)
            .where(MedicalPracticeTariff.practice_id == practice_id)
            .order_by(
                MedicalPracticeTariff.valid_from.desc(),
                MedicalPracticeTariff.created_at.desc(),
            )
        )
        if payer_id:
            stmt = stmt.where(MedicalPracticeTariff.payer_id == payer_id)
        return list((await self.session.scalars(stmt)).all())

    async def effective_tariff(
        self,
        practice_id: uuid.UUID,
        *,
        payer_id: uuid.UUID | None = None,
        health_plan_id: uuid.UUID | None = None,
        on: date | None = None,
    ) -> MedicalPracticeTariff:
        """Tariff that applies to a practice for a payer/plan on a date.

        The plan tariff wins over the payer tariff, and the payer tariff over the
        institutional one, so a plan only needs its own row when it differs.
        """

        await self.get(practice_id)
        on = on or datetime.now(UTC).date()
        tariffs = [
            tariff
            for tariff in await self.list_tariffs(practice_id)
            if tariff.valid_from <= on
            and (tariff.valid_until is None or tariff.valid_until >= on)
        ]

        def pick(**scope) -> MedicalPracticeTariff | None:
            matches = [
                tariff
                for tariff in tariffs
                if all(getattr(tariff, field) == value for field, value in scope.items())
            ]
            return max(matches, key=lambda tariff: tariff.valid_from, default=None)

        candidates = []
        if health_plan_id:
            candidates.append({"health_plan_id": health_plan_id})
        if payer_id:
            candidates.append({"payer_id": payer_id, "health_plan_id": None})
        candidates.append({"payer_id": None, "health_plan_id": None})

        for scope in candidates:
            tariff = pick(**scope)
            if tariff:
                return tariff
        raise DomainError("La práctica no tiene un valor vigente para esa cobertura", 404)

    async def create_tariff(
        self,
        practice_id: uuid.UUID,
        payload: MedicalPracticeTariffCreate,
    ) -> MedicalPracticeTariff:
        async with (
            integrity_conflict(
                self.session,
                "Ya existe un valor para esa cobertura con la misma vigencia",
            ),
            self.session.begin(),
        ):
            practice = await self.get(practice_id)
            values = await self._tariff_values(practice, payload)
            tariff = MedicalPracticeTariff(practice_id=practice_id, **values)
            self.session.add(tariff)
            await self.session.flush()
            return tariff

    async def update_tariff(
        self,
        practice_id: uuid.UUID,
        tariff_id: uuid.UUID,
        payload: MedicalPracticeTariffUpdate,
    ) -> MedicalPracticeTariff:
        async with (
            integrity_conflict(
                self.session,
                "Ya existe un valor para esa cobertura con la misma vigencia",
            ),
            self.session.begin(),
        ):
            practice = await self.get(practice_id)
            tariff = await self._require_tariff(practice_id, tariff_id)
            for field, value in (await self._tariff_values(practice, payload)).items():
                setattr(tariff, field, value)
            await self.session.flush()
            return tariff

    async def delete_tariff(self, practice_id: uuid.UUID, tariff_id: uuid.UUID) -> None:
        async with self.session.begin():
            await self.get(practice_id)
            tariff = await self._require_tariff(practice_id, tariff_id)
            await self.session.delete(tariff)

    async def _require_tariff(
        self,
        practice_id: uuid.UUID,
        tariff_id: uuid.UUID,
    ) -> MedicalPracticeTariff:
        tariff = await self.session.get(MedicalPracticeTariff, tariff_id)
        if not tariff or tariff.practice_id != practice_id:
            raise DomainError("Valor de práctica inexistente", 404)
        return tariff

    async def _tariff_values(
        self,
        practice: MedicalPractice,
        payload: MedicalPracticeTariffCreate,
    ) -> dict:
        self._validate_period(payload.valid_from, payload.valid_until)
        payer_id = payload.payer_id
        if payer_id and not await self.session.get(Payer, payer_id):
            raise DomainError("Financiador inexistente", 404)
        if payload.health_plan_id:
            plan = await self.session.get(HealthPlan, payload.health_plan_id)
            if not plan:
                raise DomainError("Plan inexistente", 404)
            if payer_id and plan.payer_id != payer_id:
                raise DomainError("El plan no pertenece al financiador informado", 422)
            # The plan always carries its payer, so the tariff can be resolved by payer too.
            payer_id = plan.payer_id

        fee = payload.professional_fee
        expense = payload.expense_amount
        if payload.unit_value is not None:
            if fee is None:
                fee = practice.galeno_units * payload.unit_value
            if expense is None:
                expense = practice.expense_units * payload.unit_value
        fee = _money(fee or Decimal(0))
        expense = _money(expense or Decimal(0))
        total = _money(payload.total_amount) if payload.total_amount is not None else fee + expense
        if total <= 0:
            raise DomainError(
                "Informe el valor de la unidad, los importes o el total de la práctica",
                422,
            )

        return {
            "payer_id": payer_id,
            "health_plan_id": payload.health_plan_id,
            "unit_value": payload.unit_value,
            "professional_fee": fee,
            "expense_amount": expense,
            "total_amount": total,
            "coinsurance": _money(payload.coinsurance),
            "currency": payload.currency.upper(),
            "valid_from": payload.valid_from,
            "valid_until": payload.valid_until,
            "notes": payload.notes,
        }

    @staticmethod
    def _validate_period(valid_from: date | None, valid_until: date | None) -> None:
        if valid_from and valid_until and valid_until < valid_from:
            raise DomainError("La vigencia informada es inválida", 422)


# Nomenclador chapter/type of the practice → category the charge is grouped under.
CHARGE_CATEGORIES: dict[PracticeType, ChargeCategory] = {
    PracticeType.CONSULTA: ChargeCategory.PROFESSIONAL_FEE,
    PracticeType.PRACTICA: ChargeCategory.PROCEDURE,
    PracticeType.CIRUGIA: ChargeCategory.PROCEDURE,
    PracticeType.ANESTESIA: ChargeCategory.PROCEDURE,
    PracticeType.LABORATORIO: ChargeCategory.LABORATORY,
    PracticeType.IMAGENES: ChargeCategory.IMAGING,
    PracticeType.INTERNACION: ChargeCategory.HOSPITALIZATION_DAY,
    PracticeType.MODULO: ChargeCategory.HOSPITALIZATION_DAY,
}

OPEN_HOSPITALIZATION_STATUSES = {
    HospitalizationStatus.PENDING_BED,
    HospitalizationStatus.IN_PROGRESS,
    HospitalizationStatus.DISCHARGE_PLANNED,
    HospitalizationStatus.CLINICALLY_DISCHARGED,
}


class HospitalizationPracticeService:
    """Practices indicated during a hospitalization, and the charges they generate."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
    ) -> list[HospitalizationPractice]:
        await self._require_hospitalization(hospitalization_id)
        return list(
            (
                await self.session.scalars(
                    select(HospitalizationPractice)
                    .options(selectinload(HospitalizationPractice.charge_item))
                    .where(HospitalizationPractice.hospitalization_id == hospitalization_id)
                    .order_by(
                        HospitalizationPractice.prescribed_at.desc(),
                        HospitalizationPractice.created_at.desc(),
                    )
                )
            ).all()
        )

    async def register(
        self,
        hospitalization_id: uuid.UUID,
        payload: HospitalizationPracticeCreate,
    ) -> HospitalizationPractice:
        async with self.session.begin():
            hospitalization = await self._require_open_hospitalization(hospitalization_id)
            practice = await self._require_active_practice(payload.practice_id)
            await self._require_professional(payload.prescribed_by_id, "prescriptor")
            if payload.performed_by_id:
                await self._require_professional(payload.performed_by_id, "ejecutor")
            if payload.service_id and not await self.session.get(Service, payload.service_id):
                raise DomainError("Servicio inexistente", 404)

            order = HospitalizationPractice(
                hospitalization_id=hospitalization_id,
                practice_id=practice.id,
                practice_code=practice.code,
                practice_name=practice.name,
                prescribed_by_id=payload.prescribed_by_id,
                performed_by_id=payload.performed_by_id,
                service_id=payload.service_id,
                status=PracticeOrderStatus.REQUESTED,
                quantity=payload.quantity,
                prescribed_at=payload.prescribed_at or datetime.now(UTC),
                indication=payload.indication,
                notes=payload.notes,
            )
            self.session.add(order)
            await self.session.flush()
            record_event(
                self.session,
                HospitalizationEventType.PRACTICE_ORDERED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=payload.recorded_by,
                occurred_at=order.prescribed_at,
                details={
                    "practice_id": str(practice.id),
                    "practice_code": practice.code,
                    "prescribed_by_id": str(payload.prescribed_by_id),
                },
            )

            if payload.performed_at:
                await self._perform(
                    order,
                    practice,
                    hospitalization,
                    performed_at=payload.performed_at,
                    performed_by_id=payload.performed_by_id,
                    unit_price=payload.unit_price,
                    recorded_by=payload.recorded_by,
                )
            await self.session.flush()
            return order

    async def perform(
        self,
        hospitalization_id: uuid.UUID,
        order_id: uuid.UUID,
        payload: HospitalizationPracticePerformCreate,
    ) -> HospitalizationPractice:
        async with self.session.begin():
            hospitalization = await self._require_open_hospitalization(hospitalization_id)
            order = await self._require_order(hospitalization_id, order_id)
            if order.status == PracticeOrderStatus.PERFORMED and not await self._charge_is_void(
                order
            ):
                raise DomainError(
                    "La práctica ya fue registrada como realizada: anule el cargo en la "
                    "cuenta para volver a facturarla",
                    409,
                )
            if order.status == PracticeOrderStatus.CANCELLED:
                raise DomainError("La práctica está anulada", 409)
            practice = await self._require_active_practice(order.practice_id)
            if payload.performed_by_id:
                await self._require_professional(payload.performed_by_id, "ejecutor")
            if payload.notes:
                order.notes = payload.notes

            await self._perform(
                order,
                practice,
                hospitalization,
                performed_at=payload.performed_at or datetime.now(UTC),
                performed_by_id=payload.performed_by_id or order.performed_by_id,
                unit_price=payload.unit_price,
                recorded_by=payload.recorded_by,
            )
            await self.session.flush()
            return order

    async def cancel(
        self,
        hospitalization_id: uuid.UUID,
        order_id: uuid.UUID,
        payload: HospitalizationPracticeCancelCreate,
    ) -> HospitalizationPractice:
        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            order = await self._require_order(hospitalization_id, order_id)
            if order.status == PracticeOrderStatus.PERFORMED and not await self._charge_is_void(
                order
            ):
                raise DomainError(
                    "La práctica realizada tiene un cargo activo: anúlelo en la cuenta antes "
                    "de anular la práctica",
                    409,
                )
            if order.status == PracticeOrderStatus.CANCELLED:
                return order

            now = datetime.now(UTC)
            order.status = PracticeOrderStatus.CANCELLED
            order.cancelled_at = now
            if payload.reason:
                order.notes = payload.reason
            record_event(
                self.session,
                HospitalizationEventType.PRACTICE_CANCELLED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=payload.actor,
                occurred_at=now,
                details={"practice_code": order.practice_code, "reason": payload.reason},
            )
            await self.session.flush()
            return order

    async def _perform(
        self,
        order: HospitalizationPractice,
        practice: MedicalPractice,
        hospitalization: Hospitalization,
        *,
        performed_at: datetime,
        performed_by_id: uuid.UUID | None,
        unit_price: Decimal | None,
        recorded_by: str | None,
    ) -> None:
        """Register the performance and charge it to the account of the hospitalization."""

        account = await require_open_account(self.session, order.hospitalization_id)
        price = await self._unit_price(
            practice,
            account.coverage_id,
            on=performed_at.date(),
            override=unit_price,
        )
        item = add_charge(
            self.session,
            account,
            category=CHARGE_CATEGORIES.get(practice.practice_type, ChargeCategory.OTHER),
            description=f"{practice.code} - {practice.name}",
            quantity=order.quantity,
            unit_price=price,
            charged_at=performed_at,
            recorded_by=recorded_by,
            notes=order.indication,
            practice_id=practice.id,
            practice_code=practice.code,
        )
        await self.session.flush()

        order.status = PracticeOrderStatus.PERFORMED
        order.performed_at = performed_at
        order.performed_by_id = performed_by_id
        order.charge_item_id = item.id
        record_event(
            self.session,
            HospitalizationEventType.PRACTICE_PERFORMED,
            hospitalization_id=order.hospitalization_id,
            patient_id=hospitalization.patient_id,
            actor=recorded_by,
            occurred_at=performed_at,
            details={
                "practice_code": practice.code,
                "charge_item_id": str(item.id),
                "amount": str(item.amount),
            },
        )

    async def _unit_price(
        self,
        practice: MedicalPractice,
        coverage_id: uuid.UUID | None,
        *,
        on: date,
        override: Decimal | None,
    ) -> Decimal:
        if override is not None:
            return _money(override)

        payer_id: uuid.UUID | None = None
        health_plan_id: uuid.UUID | None = None
        if coverage_id:
            coverage = await self.session.get(PatientCoverage, coverage_id)
            if coverage:
                payer_id = coverage.payer_id
                health_plan_id = coverage.health_plan_id
        try:
            tariff = await MedicalPracticeService(self.session).effective_tariff(
                practice.id,
                payer_id=payer_id,
                health_plan_id=health_plan_id,
                on=on,
            )
        except DomainError as missing:
            raise DomainError(
                f"La práctica {practice.code} no tiene un valor vigente para la cobertura "
                "de la internación: informe el importe",
                422,
            ) from missing
        return tariff.total_amount

    async def _charge_is_void(self, order: HospitalizationPractice) -> bool:
        """A performed practice can be re-charged or annulled once its charge is voided."""

        if not order.charge_item_id:
            return True
        item = await self.session.get(ChargeItem, order.charge_item_id)
        return item is None or item.status == ChargeItemStatus.VOID

    async def _require_hospitalization(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _require_open_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
    ) -> Hospitalization:
        hospitalization = await self._require_hospitalization(hospitalization_id)
        if hospitalization.status not in OPEN_HOSPITALIZATION_STATUSES:
            raise DomainError("La internación ya no admite prácticas", 409)
        return hospitalization

    async def _require_active_practice(self, practice_id: uuid.UUID) -> MedicalPractice:
        practice = await MedicalPracticeService(self.session).get(practice_id)
        if not practice.is_active:
            raise DomainError("La práctica no está vigente en el nomenclador", 409)
        return practice

    async def _require_professional(self, professional_id: uuid.UUID, role: str) -> Professional:
        professional = await self.session.get(Professional, professional_id)
        if not professional:
            raise DomainError(f"Profesional {role} inexistente", 404)
        return professional

    async def _require_order(
        self,
        hospitalization_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> HospitalizationPractice:
        order = await self.session.get(HospitalizationPractice, order_id)
        if not order or order.hospitalization_id != hospitalization_id:
            raise DomainError("Práctica de la internación inexistente", 404)
        return order
