"""Practices performed during a hospitalization and the charges they generate."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import DomainError
from app.models.account import (
    Account,
    AccountStatus,
    ChargeCategory,
    ChargeItem,
    ChargeItemStatus,
)
from app.models.audit import HospitalizationEventType
from app.models.coverage import HealthPlan, Payer
from app.models.practice import Nomenclador, PracticeChapter, PracticeOrderStatus, PracticeType
from app.schemas.practice import (
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticeCreate,
    HospitalizationPracticePerformCreate,
    MedicalPracticeCreate,
    MedicalPracticeTariffCreate,
)
from app.schemas.workflow import ChargeItemCreate, ChargeItemVoidCreate
from app.services.account import AccountService
from app.services.audit import list_events
from app.services.practice import HospitalizationPracticeService, MedicalPracticeService
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

PERFORMED_AT = datetime(2026, 6, 1, 10, 30, tzinfo=UTC)


def practice_payload(**overrides) -> MedicalPracticeCreate:
    data: dict = {
        "nomenclador": Nomenclador.NACIONAL,
        "code": "42.01.01",
        "name": "Consulta en consultorio",
        "chapter": PracticeChapter.CONSULTAS,
        "practice_type": PracticeType.CONSULTA,
        "galeno_units": Decimal(40),
        "expense_units": Decimal(10),
    }
    data.update(overrides)
    return MedicalPracticeCreate(**data)


async def catalog_practice(session, *, with_tariff: bool = True, **overrides):
    """A practice in the catalog, with its institutional tariff of $5000."""

    practice = await MedicalPracticeService(session).create(practice_payload(**overrides))
    if with_tariff:
        await MedicalPracticeService(session).create_tariff(
            practice.id,
            MedicalPracticeTariffCreate(unit_value=Decimal(100), valid_from=date(2026, 1, 1)),
        )
    return practice


def test_a_performed_practice_charges_the_account_with_the_agreed_value():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    quantity=Decimal(2),
                    performed_at=PERFORMED_AT,
                    indication="Control post quirúrgico",
                    recorded_by="Enfermería",
                ),
            )
            assert order.status == PracticeOrderStatus.PERFORMED
            assert order.practice_code == "42.01.01"
            assert order.prescribed_by_id == scenario.practitioner_id
            assert order.charge_item_id is not None

        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            item = account.charge_items[0]
            # 2 consultas a $5000 cada una.
            assert item.unit_price == Decimal("5000.00")
            assert item.amount == Decimal("10000.00")
            assert item.category == ChargeCategory.PROFESSIONAL_FEE
            assert item.practice_id == practice.id
            assert item.practice_code == "42.01.01"
            assert item.description == "42.01.01 - Consulta en consultorio"
            assert AccountService.total(account) == Decimal("10000.00")

    run_db(case)


def test_the_charge_takes_the_value_of_the_coverage_of_the_hospitalization():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer = Payer(name="OSDE", code="OSDE")
            setup.add(payer)
            await setup.flush()
            plan = HealthPlan(payer_id=payer.id, name="310", code="310")
            setup.add(plan)
            await setup.commit()
            payer_id, plan_id = payer.id, plan.id
        async with factory() as session:
            practice = await catalog_practice(session)
            await MedicalPracticeService(session).create_tariff(
                practice.id,
                MedicalPracticeTariffCreate(
                    health_plan_id=plan_id,
                    unit_value=Decimal(150),
                    valid_from=date(2026, 1, 1),
                ),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(
                session,
                scenario,
                coverage={
                    "payer_id": payer_id,
                    "health_plan_id": plan_id,
                    "member_number": "998877",
                },
            )
        async with factory() as session:
            await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            # El plan 310 paga la unidad a $150: 40 galeno + 10 gastos.
            assert account.charge_items[0].unit_price == Decimal("7500.00")

    run_db(case)


def test_an_indicated_practice_is_only_charged_when_it_is_performed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                ),
            )
            assert order.status == PracticeOrderStatus.REQUESTED
            assert order.charge_item_id is None
            order_id = order.id
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            assert account.charge_items == []
        async with factory() as session:
            performed = await HospitalizationPracticeService(session).perform(
                hospitalization_id,
                order_id,
                HospitalizationPracticePerformCreate(
                    performed_at=PERFORMED_AT,
                    performed_by_id=scenario.practitioner_id,
                ),
            )
            assert performed.status == PracticeOrderStatus.PERFORMED
            assert performed.performed_by_id == scenario.practitioner_id
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            assert len(account.charge_items) == 1
        async with factory() as session:
            with pytest.raises(DomainError) as twice:
                await HospitalizationPracticeService(session).perform(
                    hospitalization_id,
                    order_id,
                    HospitalizationPracticePerformCreate(performed_at=PERFORMED_AT),
                )
            assert twice.value.status_code == 409

    run_db(case)


def test_a_practice_without_agreed_value_needs_the_amount():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session, with_tariff=False)
        async with factory() as session:
            with pytest.raises(DomainError) as missing:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.practitioner_id,
                        performed_at=PERFORMED_AT,
                    ),
                )
            assert missing.value.status_code == 422
        async with factory() as session:
            # Nothing was left behind by the failed registration.
            assert (await session.scalars(select(ChargeItem))).all() == []
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                    unit_price=Decimal("1234.50"),
                ),
            )
            assert order.status == PracticeOrderStatus.PERFORMED
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            assert account.charge_items[0].amount == Decimal("1234.50")

    run_db(case)


def test_a_performed_practice_cannot_be_cancelled_but_an_indicated_one_can():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            service = HospitalizationPracticeService(session)
            indicated = await service.register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                ),
            )
            indicated_id = indicated.id
        async with factory() as session:
            performed = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            performed_id = performed.id
        async with factory() as session:
            cancelled = await HospitalizationPracticeService(session).cancel(
                hospitalization_id,
                indicated_id,
                HospitalizationPracticeCancelCreate(reason="Se suspende la indicación"),
            )
            assert cancelled.status == PracticeOrderStatus.CANCELLED
            assert cancelled.cancelled_at is not None
        async with factory() as session:
            with pytest.raises(DomainError) as charged:
                await HospitalizationPracticeService(session).cancel(
                    hospitalization_id,
                    performed_id,
                    HospitalizationPracticeCancelCreate(),
                )
            assert charged.value.status_code == 409

    run_db(case)


def test_the_prescribing_professional_must_exist_and_the_practice_must_be_active():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
            inactive = await catalog_practice(
                session,
                code="15.01.02",
                name="Cirugía dada de baja",
                chapter=PracticeChapter.CIRUGIA,
                practice_type=PracticeType.CIRUGIA,
                is_active=False,
            )
        async with factory() as session:
            service = HospitalizationPracticeService(session)
            with pytest.raises(DomainError) as unknown:
                await service.register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.patient_id,
                    ),
                )
            assert unknown.value.status_code == 404
        async with factory() as session:
            with pytest.raises(DomainError) as retired:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=inactive.id,
                        prescribed_by_id=scenario.practitioner_id,
                    ),
                )
            assert retired.value.status_code == 409

    run_db(case)


def test_practices_cannot_be_charged_to_a_closed_account():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            account = await session.scalar(
                select(Account).where(Account.hospitalization_id == hospitalization_id)
            )
            account.status = AccountStatus.CLOSED
            await session.commit()
        async with factory() as session:
            with pytest.raises(DomainError) as closed:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.practitioner_id,
                        performed_at=PERFORMED_AT,
                    ),
                )
            assert closed.value.status_code == 409

    run_db(case)


def test_the_practice_lifecycle_is_in_the_audit_trail():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
        async with factory() as session:
            types = [event.event_type for event in await list_events(session, hospitalization_id)]
            assert HospitalizationEventType.PRACTICE_ORDERED in types
            assert HospitalizationEventType.PRACTICE_PERFORMED in types

    run_db(case)


def test_a_manual_charge_can_also_point_at_a_practice():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            item = await AccountService(session).add_charge_item(
                hospitalization_id,
                ChargeItemCreate(
                    practice_id=practice.id,
                    category=ChargeCategory.PROCEDURE,
                    description="Ajuste manual de la práctica",
                    unit_price=Decimal("1000.00"),
                ),
            )
            assert item.practice_id == practice.id
            assert item.practice_code == "42.01.01"

    run_db(case)


def test_voiding_a_charge_keeps_the_line_and_takes_it_out_of_the_total():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            charge_item_id = order.charge_item_id
        async with factory() as session:
            item = await AccountService(session).void_charge_item(
                hospitalization_id,
                charge_item_id,
                ChargeItemVoidCreate(reason="Cargada por error", actor="Facturación"),
            )
            assert item.status == ChargeItemStatus.VOID
            assert item.void_reason == "Cargada por error"
            assert item.voided_by == "Facturación"
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            # La línea sigue en la cuenta, pero ya no suma.
            assert len(account.charge_items) == 1
            assert AccountService.total(account) == Decimal(0)
            assert AccountService.voided_total(account) == Decimal("5000.00")
        async with factory() as session:
            types = [event.event_type for event in await list_events(session, hospitalization_id)]
            assert HospitalizationEventType.CHARGE_ITEM_VOIDED in types

    run_db(case)


def test_voiding_a_charge_twice_is_harmless_and_an_unknown_charge_is_rejected():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            charge_item_id = order.charge_item_id
        async with factory() as session:
            await AccountService(session).void_charge_item(
                hospitalization_id,
                charge_item_id,
                ChargeItemVoidCreate(),
            )
        async with factory() as session:
            again = await AccountService(session).void_charge_item(
                hospitalization_id,
                charge_item_id,
                ChargeItemVoidCreate(reason="Otra vez"),
            )
            assert again.status == ChargeItemStatus.VOID
            assert again.void_reason is None
        async with factory() as session:
            with pytest.raises(DomainError) as unknown:
                await AccountService(session).void_charge_item(
                    hospitalization_id,
                    uuid.uuid4(),
                    ChargeItemVoidCreate(),
                )
            assert unknown.value.status_code == 404

    run_db(case)


def test_a_closed_account_does_not_accept_voiding_charges():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            charge_item_id = order.charge_item_id
        async with factory() as session:
            account = await session.scalar(
                select(Account).where(Account.hospitalization_id == hospitalization_id)
            )
            account.status = AccountStatus.CLOSED
            await session.commit()
        async with factory() as session:
            with pytest.raises(DomainError) as closed:
                await AccountService(session).void_charge_item(
                    hospitalization_id,
                    charge_item_id,
                    ChargeItemVoidCreate(),
                )
            assert closed.value.status_code == 409

    run_db(case)


def test_a_practice_with_a_voided_charge_can_be_recharged_or_annulled():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            order_id, first_charge_id = order.id, order.charge_item_id
        async with factory() as session:
            # Con el cargo activo, la práctica realizada no se toca.
            with pytest.raises(DomainError) as active:
                await HospitalizationPracticeService(session).cancel(
                    hospitalization_id,
                    order_id,
                    HospitalizationPracticeCancelCreate(),
                )
            assert active.value.status_code == 409
        async with factory() as session:
            await AccountService(session).void_charge_item(
                hospitalization_id,
                first_charge_id,
                ChargeItemVoidCreate(reason="Importe equivocado"),
            )
        async with factory() as session:
            # Anulado el cargo, se puede volver a facturar con el importe correcto.
            recharged = await HospitalizationPracticeService(session).perform(
                hospitalization_id,
                order_id,
                HospitalizationPracticePerformCreate(
                    performed_at=PERFORMED_AT,
                    unit_price=Decimal("4200.00"),
                ),
            )
            assert recharged.charge_item_id != first_charge_id
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            assert len(account.charge_items) == 2
            assert AccountService.total(account) == Decimal("4200.00")
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            active_item = next(
                item for item in account.charge_items if item.status == ChargeItemStatus.ACTIVE
            ).id
        async with factory() as session:
            await AccountService(session).void_charge_item(
                hospitalization_id,
                active_item,
                ChargeItemVoidCreate(reason="Se anula la práctica"),
            )
        async with factory() as session:
            cancelled = await HospitalizationPracticeService(session).cancel(
                hospitalization_id,
                order_id,
                HospitalizationPracticeCancelCreate(reason="No correspondía"),
            )
            assert cancelled.status == PracticeOrderStatus.CANCELLED
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            assert AccountService.total(account) == Decimal(0)
            assert AccountService.voided_total(account) == Decimal("9200.00")

    run_db(case)
