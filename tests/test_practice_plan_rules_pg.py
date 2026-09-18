"""La cartilla del plan aplicada al indicar y realizar prácticas en una internación."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.models.account import ChargeCategory, ChargeItemStatus
from app.models.coverage import HealthPlan, Payer
from app.models.practice import Nomenclador, PlanCoverageStatus, PracticeChapter, PracticeType
from app.schemas.practice import (
    HealthPlanPracticeCreate,
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticeCreate,
    HospitalizationPracticePerformCreate,
    MedicalPracticeCreate,
    MedicalPracticeTariffCreate,
)
from app.schemas.workflow import ChargeItemVoidCreate
from app.services.account import AccountService
from app.services.audit import list_events
from app.services.plan_coverage import HealthPlanPracticeService
from app.services.practice import HospitalizationPracticeService, MedicalPracticeService
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

PERFORMED_AT = datetime(2026, 6, 1, 10, 30, tzinfo=UTC)
COVERAGE_FROM = date(2026, 5, 1)


async def build_plan(session) -> tuple:
    payer = Payer(name="OSDE", code="OSDE")
    session.add(payer)
    await session.flush()
    plan = HealthPlan(payer_id=payer.id, name="210", code="210")
    session.add(plan)
    await session.commit()
    return payer.id, plan.id


async def catalog_practice(session, **overrides):
    """Práctica del nomenclador con arancel institucional de $5000."""

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
    service = MedicalPracticeService(session)
    practice = await service.create(MedicalPracticeCreate(**data))
    await service.create_tariff(
        practice.id,
        MedicalPracticeTariffCreate(unit_value=Decimal(100), valid_from=date(2026, 1, 1)),
    )
    return practice


async def hospitalization_with_plan(session, scenario, payer_id, plan_id, **coverage):
    data = {
        "payer_id": payer_id,
        "health_plan_id": plan_id,
        "valid_from": COVERAGE_FROM,
        "member_number": "998877",
    }
    data.update(coverage)
    return await hospitalization_from_admission(session, scenario, coverage=data)


def test_a_plan_without_cartilla_does_not_block_anything():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            return order.copayment_amount
        # Una cartilla vacía significa que nadie la cargó, no que el plan no cubra nada.

    assert run_db(case) == Decimal("0.00")


def test_a_practice_outside_the_cartilla_is_rejected():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            covered = await catalog_practice(session)
            other = await catalog_practice(session, code="34.07.01", name="Resonancia")
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id, HealthPlanPracticeCreate(practice_id=covered.id)
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=other.id,
                        prescribed_by_id=scenario.practitioner_id,
                    ),
                )
            return excinfo.value.status_code, excinfo.value.message

    status_code, message = run_db(case)
    assert status_code == 409
    assert "no está en la cartilla" in message


def test_a_practice_excluded_by_the_plan_is_rejected_but_can_be_forced():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(practice_id=practice.id, is_covered=False),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.practitioner_id,
                    ),
                )
            rejected = excinfo.value.message
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.practitioner_id,
                        override_coverage_rules=True,
                    ),
                )
            without_reason = excinfo.value.status_code
        async with factory() as session:
            forced = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    override_coverage_rules=True,
                    override_reason="Urgencia: se factura al paciente",
                ),
            )
            reason = forced.coverage_override_reason
        async with factory() as session:
            events = await list_events(session, hospitalization_id)
        overrides = [
            event for event in events if (event.details or {}).get("coverage_override") == "true"
        ]
        return rejected, without_reason, reason, len(overrides)

    rejected, without_reason, reason, overrides = run_db(case)
    assert "no cubre" in rejected
    assert without_reason == 422
    assert reason == "Urgencia: se factura al paciente"
    assert overrides == 1


def test_a_practice_in_waiting_period_is_rejected_until_the_period_is_over():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(practice_id=practice.id, waiting_period_days=90),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.practitioner_id,
                        # 31 días después del alta de la cobertura, con 90 de carencia.
                        performed_at=PERFORMED_AT,
                    ),
                )
            blocked = excinfo.value.message
        async with factory() as session:
            after = datetime.combine(
                COVERAGE_FROM + timedelta(days=91), datetime.min.time(), tzinfo=UTC
            )
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=after,
                ),
            )
            return blocked, order.status.value

    blocked, status = run_db(case)
    assert "carencia hasta el 2026-07-30" in blocked
    assert status == "PERFORMED"


def test_a_practice_the_plan_authorizes_needs_the_number_of_the_payer():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(
                    practice_id=practice.id, requires_authorization=True
                ),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.practitioner_id,
                    ),
                )
            blocked = excinfo.value.status_code, excinfo.value.message
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    authorization_number="AUT-99123",
                ),
            )
            return blocked, order.authorization_number

    (status_code, message), number = run_db(case)
    assert status_code == 409
    assert "exige autorización" in message
    assert number == "AUT-99123"


def test_the_copayment_of_the_plan_is_charged_as_its_own_line():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(
                    practice_id=practice.id, copayment_amount=Decimal("1200.00")
                ),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    quantity=Decimal(2),
                    performed_at=PERFORMED_AT,
                ),
            )
            order_id = order.id
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            charges = {item.description: item for item in account.charge_items}
            copayment = next(
                item for item in account.charge_items if item.description.startswith("Copago")
            )
            return (
                len(charges),
                copayment.amount,
                copayment.category,
                AccountService.total(account),
                order_id,
            )

    lines, copayment, category, total, _ = run_db(case)
    assert lines == 2
    # El copago es por práctica: dos consultas, $1200 cada una.
    assert copayment == Decimal("2400.00")
    assert category is ChargeCategory.OTHER
    assert total == Decimal("12400.00")


def test_cancelling_the_practice_voids_its_copayment():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(
                    practice_id=practice.id, copayment_amount=Decimal("1200.00")
                ),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            order_id, charge_id = order.id, order.charge_item_id
        async with factory() as session:
            await AccountService(session).void_charge_item(
                hospitalization_id, charge_id, ChargeItemVoidCreate(reason="Error de carga")
            )
        async with factory() as session:
            await HospitalizationPracticeService(session).cancel(
                hospitalization_id,
                order_id,
                HospitalizationPracticeCancelCreate(reason="Se suspende"),
            )
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            return (
                [item.status for item in account.charge_items],
                AccountService.total(account),
            )

    statuses, total = run_db(case)
    assert statuses == [ChargeItemStatus.VOID, ChargeItemStatus.VOID]
    assert total == Decimal("0.00")


def test_the_coverage_check_answers_before_indicating_the_practice():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(
                    practice_id=practice.id,
                    waiting_period_days=90,
                    copayment_amount=Decimal("1200.00"),
                    requires_authorization=True,
                ),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            service = HospitalizationPracticeService(session)
            in_waiting = await service.coverage_check(
                hospitalization_id, practice.id, on=date(2026, 6, 1)
            )
            covered = await service.coverage_check(
                hospitalization_id, practice.id, on=date(2026, 9, 1)
            )
            return in_waiting, covered

    in_waiting, covered = run_db(case)
    assert in_waiting.status is PlanCoverageStatus.WAITING_PERIOD
    assert in_waiting.blocked
    assert in_waiting.available_from == date(2026, 7, 30)
    assert covered.status is PlanCoverageStatus.COVERED
    assert not covered.blocked
    assert covered.copayment_amount == Decimal("1200.00")
    assert covered.requires_authorization


def test_a_private_patient_is_not_affected_by_any_cartilla():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            hospitalization_id = await hospitalization_from_admission(setup, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            check = await HospitalizationPracticeService(session).coverage_check(
                hospitalization_id, practice.id
            )
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            return check.status, order.copayment_amount

    status, copayment = run_db(case)
    assert status is PlanCoverageStatus.NO_COVERAGE
    assert copayment == Decimal("0.00")


def test_a_practice_forced_at_prescription_stays_forced_when_performed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(practice_id=practice.id, is_covered=False),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    override_coverage_rules=True,
                    override_reason="Urgencia",
                ),
            )
            order_id = order.id
        async with factory() as session:
            performed = await HospitalizationPracticeService(session).perform(
                hospitalization_id,
                order_id,
                HospitalizationPracticePerformCreate(performed_at=PERFORMED_AT),
            )
            return performed.status.value, performed.charge_item_id is not None

    status, charged = run_db(case)
    assert status == "PERFORMED"
    assert charged


def test_the_waiting_period_of_the_practice_applies_when_the_plan_did_not_agree_one():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session, default_waiting_period_days=90)
            practice_id = practice.id
        async with factory() as session:
            # La cartilla no pacta carencia: rige la de la práctica.
            await HealthPlanPracticeService(session).link(
                plan_id, HealthPlanPracticeCreate(practice_id=practice_id)
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await HospitalizationPracticeService(session).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice_id,
                        prescribed_by_id=scenario.practitioner_id,
                        performed_at=PERFORMED_AT,
                    ),
                )
            return excinfo.value.message

    assert "carencia hasta el 2026-07-30" in run_db(case)


def test_the_plan_can_shorten_the_waiting_period_of_the_practice():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session, default_waiting_period_days=90)
            practice_id = practice.id
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(practice_id=practice_id, waiting_period_days=0),
            )
        async with factory() as session:
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id
            )
        async with factory() as session:
            order = await HospitalizationPracticeService(session).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice_id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            return order.status.value

    assert run_db(case) == "PERFORMED"


def test_a_coverage_without_a_catalog_plan_says_so_instead_of_staying_silent():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            # Cobertura cargada a mano, como la que trae el carnet del paciente.
            hospitalization_id = await hospitalization_from_admission(
                setup, scenario, coverage={"payer_name": "OMINT", "plan_name": "4500"}
            )
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            check = await HospitalizationPracticeService(session).coverage_check(
                hospitalization_id, practice.id
            )
            return check.status, check.message

    status, message = run_db(case)
    assert status is PlanCoverageStatus.NO_PLAN
    assert "no está vinculada a un plan del catálogo" in message


def test_a_waiting_period_that_cannot_be_counted_is_reported_without_blocking():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            payer_id, plan_id = await build_plan(setup)
        async with factory() as session:
            practice = await catalog_practice(session, default_waiting_period_days=90)
            practice_id = practice.id
        async with factory() as session:
            await HealthPlanPracticeService(session).link(
                plan_id, HealthPlanPracticeCreate(practice_id=practice_id)
            )
        async with factory() as session:
            # Cobertura del plan, pero sin fecha de alta: no hay desde cuándo contar.
            hospitalization_id = await hospitalization_with_plan(
                session, scenario, payer_id, plan_id, valid_from=None
            )
        async with factory() as session:
            check = await HospitalizationPracticeService(session).coverage_check(
                hospitalization_id, practice_id
            )
            return check.status, check.blocked, check.waiting_period_days, check.message

    status, blocked, waiting, message = run_db(case)
    assert status is PlanCoverageStatus.COVERED
    assert not blocked
    assert waiting == 90
    assert "no tiene fecha de alta" in message
