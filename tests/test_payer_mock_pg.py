"""API mock del financiador: qué contesta al código de autorización del afiliado."""

from datetime import date
from decimal import Decimal

from app.models.practice import MedicalPractice, Nomenclador, PracticeChapter, PracticeType
from app.schemas.payer_mock import PayerAuthorizationRequest, PayerAuthorizationResult
from app.schemas.practice import HealthPlanPracticeCreate, MedicalPracticeTariffCreate
from app.schemas.workflow import HealthPlanCreate, PayerCreate
from app.services.payer_mock import PayerAuthorizationMock
from app.services.plan_coverage import HealthPlanPracticeService
from app.services.practice import MedicalPracticeService
from app.services.registry import CoverageService
from tests.conftest import requires_postgres, run_db

pytestmark = requires_postgres


async def build_plan_with_practice(session, *, is_covered: bool = True):
    """Un plan con una práctica en cartilla con copago, y su valor particular cargado."""

    coverage = CoverageService(session)
    payer = await coverage.create_payer(PayerCreate(name="OSDE", code="OSDE"))
    plan = await coverage.create_health_plan(payer.id, HealthPlanCreate(name="210", code="210"))
    practice = MedicalPractice(
        nomenclador=Nomenclador.NACIONAL,
        code="34.07.01",
        name="Resonancia magnetica de cerebro",
        chapter=PracticeChapter.DIAGNOSTICO_POR_IMAGENES,
        practice_type=PracticeType.IMAGENES,
    )
    session.add(practice)
    await session.commit()
    await HealthPlanPracticeService(session).link(
        plan.id,
        HealthPlanPracticeCreate(
            practice_id=practice.id,
            is_covered=is_covered,
            copayment_amount=Decimal("4500.00"),
            requires_authorization=True,
        ),
    )
    await MedicalPracticeService(session).create_tariff(
        practice.id,
        MedicalPracticeTariffCreate(
            total_amount=Decimal("80000.00"),
            valid_from=date(2020, 1, 1),
        ),
    )
    return plan, practice


def verify(code: str, *, is_covered: bool = True):
    async def case(factory):
        async with factory() as session:
            plan, practice = await build_plan_with_practice(session, is_covered=is_covered)
            return await PayerAuthorizationMock(session).verify(
                PayerAuthorizationRequest(
                    health_plan_id=plan.id,
                    authorization_code=code,
                    practice_id=practice.id,
                )
            )

    return run_db(case)


def test_an_even_code_is_authorized_and_leaves_the_copayment_to_the_patient():
    answer = verify("124")

    assert answer.authorized
    assert answer.result is PayerAuthorizationResult.AUTHORIZED
    assert answer.authorization_number.startswith("OSDE-")
    assert answer.copayment_amount == Decimal("4500.00")
    # Autorizada, el paciente solo pone el copago de la cartilla.
    assert answer.patient_due == Decimal("4500.00")


def test_an_odd_code_is_rejected_and_the_practice_is_offered_as_private():
    answer = verify("123")

    assert not answer.authorized
    assert answer.result is PayerAuthorizationResult.REJECTED
    assert answer.authorization_number is None
    assert answer.private_amount == Decimal("80000.00")
    # Sin autorización lo paga el paciente: el valor particular, no el copago.
    assert answer.patient_due == Decimal("80000.00")


def test_a_code_that_is_not_three_digits_is_not_validated():
    answer = verify("12")

    assert not answer.authorized
    assert answer.result is PayerAuthorizationResult.INVALID_CODE
    assert answer.patient_due == Decimal("80000.00")


def test_the_payer_does_not_recognise_the_zero_code():
    answer = verify("000")

    assert not answer.authorized
    assert answer.result is PayerAuthorizationResult.UNKNOWN_CODE


def test_a_practice_out_of_the_cartilla_is_not_authorized_by_any_code():
    answer = verify("124", is_covered=False)

    assert not answer.authorized
    assert answer.result is PayerAuthorizationResult.NOT_COVERED
    # Fuera de cartilla no hay copago que cobrar: se cobra el valor particular.
    assert answer.copayment_amount == Decimal(0)
    assert answer.patient_due == Decimal("80000.00")


def test_without_a_practice_the_payer_only_validates_the_code():
    async def case(factory):
        async with factory() as session:
            plan, _ = await build_plan_with_practice(session)
            return await PayerAuthorizationMock(session).verify(
                PayerAuthorizationRequest(health_plan_id=plan.id, authorization_code="248")
            )

    answer = run_db(case)
    assert answer.authorized
    assert answer.practice_id is None
    assert answer.private_amount is None
    assert answer.patient_due == Decimal(0)
