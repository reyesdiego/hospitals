"""Medical practice catalog and per-payer tariffs against PostgreSQL."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.models.coverage import HealthPlan, Payer
from app.models.practice import Nomenclador, PracticeChapter, PracticeSetting, PracticeType
from app.schemas.practice import (
    MedicalPracticeCreate,
    MedicalPracticeTariffCreate,
    MedicalPracticeUpdate,
)
from app.services.practice import MedicalPracticeService
from tests.conftest import requires_postgres, run_db

pytestmark = requires_postgres


def practice_payload(**overrides) -> MedicalPracticeCreate:
    data: dict = {
        "nomenclador": Nomenclador.NACIONAL,
        "code": "42.01.01",
        "name": "Consulta en consultorio",
        "chapter": PracticeChapter.CONSULTAS,
        "practice_type": PracticeType.CONSULTA,
        "setting": PracticeSetting.AMBULATORIO,
        "galeno_units": Decimal(40),
        "expense_units": Decimal(10),
    }
    data.update(overrides)
    return MedicalPracticeCreate(**data)


async def build_payer(session) -> tuple[Payer, HealthPlan]:
    payer = Payer(name="OSDE", code="OSDE")
    session.add(payer)
    await session.flush()
    plan = HealthPlan(payer_id=payer.id, name="210", code="210")
    session.add(plan)
    await session.commit()
    return payer, plan


def test_code_is_unique_inside_the_nomenclador_but_not_across_nomencladores():
    async def case(factory):
        async with factory() as session:
            await MedicalPracticeService(session).create(practice_payload())
        async with factory() as session:
            with pytest.raises(DomainError) as conflict:
                await MedicalPracticeService(session).create(practice_payload(name="Duplicada"))
            assert conflict.value.status_code == 409
        async with factory() as session:
            # The same code belongs to a different practice in another nomenclador.
            other = await MedicalPracticeService(session).create(
                practice_payload(nomenclador=Nomenclador.PROPIO, name="Consulta institucional")
            )
            assert other.nomenclador == Nomenclador.PROPIO

    run_db(case)


def test_tariff_amounts_are_derived_from_the_units_of_the_practice():
    async def case(factory):
        async with factory() as session:
            practice = await MedicalPracticeService(session).create(practice_payload())
            practice_id = practice.id
        async with factory() as session:
            tariff = await MedicalPracticeService(session).create_tariff(
                practice_id,
                MedicalPracticeTariffCreate(unit_value=Decimal(100), valid_from=date(2026, 1, 1)),
            )
            # 40 unidades galeno de honorarios y 10 de gastos, a $100 la unidad.
            assert tariff.professional_fee == Decimal("4000.00")
            assert tariff.expense_amount == Decimal("1000.00")
            assert tariff.total_amount == Decimal("5000.00")
            assert tariff.currency == "ARS"

    run_db(case)


def test_a_tariff_without_value_is_rejected():
    async def case(factory):
        async with factory() as session:
            practice_id = (await MedicalPracticeService(session).create(practice_payload())).id
        async with factory() as session:
            with pytest.raises(DomainError) as invalid:
                await MedicalPracticeService(session).create_tariff(
                    practice_id,
                    MedicalPracticeTariffCreate(valid_from=date(2026, 1, 1)),
                )
            assert invalid.value.status_code == 422

    run_db(case)


def test_the_institutional_tariff_cannot_be_loaded_twice_for_the_same_date():
    async def case(factory):
        async with factory() as session:
            practice_id = (await MedicalPracticeService(session).create(practice_payload())).id
        payload = MedicalPracticeTariffCreate(
            unit_value=Decimal(100),
            valid_from=date(2026, 1, 1),
        )
        async with factory() as session:
            await MedicalPracticeService(session).create_tariff(practice_id, payload)
        async with factory() as session:
            with pytest.raises(DomainError) as conflict:
                await MedicalPracticeService(session).create_tariff(practice_id, payload)
            assert conflict.value.status_code == 409

    run_db(case)


def test_effective_tariff_prefers_the_plan_over_the_payer_and_the_institution():
    async def case(factory):
        async with factory() as setup:
            payer, plan = await build_payer(setup)
            practice_id = (await MedicalPracticeService(setup).create(practice_payload())).id
        async with factory() as session:
            service = MedicalPracticeService(session)
            await service.create_tariff(
                practice_id,
                MedicalPracticeTariffCreate(
                    unit_value=Decimal(100),
                    valid_from=date(2026, 1, 1),
                ),
            )
            await service.create_tariff(
                practice_id,
                MedicalPracticeTariffCreate(
                    payer_id=payer.id,
                    unit_value=Decimal(120),
                    valid_from=date(2026, 1, 1),
                ),
            )
            await service.create_tariff(
                practice_id,
                MedicalPracticeTariffCreate(
                    health_plan_id=plan.id,
                    unit_value=Decimal(150),
                    valid_from=date(2026, 1, 1),
                ),
            )
        async with factory() as session:
            service = MedicalPracticeService(session)
            institutional = await service.effective_tariff(practice_id, on=date(2026, 6, 1))
            assert institutional.total_amount == Decimal("5000.00")

            by_payer = await service.effective_tariff(
                practice_id,
                payer_id=payer.id,
                on=date(2026, 6, 1),
            )
            assert by_payer.total_amount == Decimal("6000.00")

            by_plan = await service.effective_tariff(
                practice_id,
                payer_id=payer.id,
                health_plan_id=plan.id,
                on=date(2026, 6, 1),
            )
            assert by_plan.total_amount == Decimal("7500.00")

    run_db(case)


def test_effective_tariff_ignores_values_outside_their_period():
    async def case(factory):
        async with factory() as session:
            practice_id = (await MedicalPracticeService(session).create(practice_payload())).id
        async with factory() as session:
            await MedicalPracticeService(session).create_tariff(
                practice_id,
                MedicalPracticeTariffCreate(
                    unit_value=Decimal(100),
                    valid_from=date(2026, 1, 1),
                    valid_until=date(2026, 3, 31),
                ),
            )
        async with factory() as session:
            service = MedicalPracticeService(session)
            assert (await service.effective_tariff(practice_id, on=date(2026, 2, 1))) is not None
            with pytest.raises(DomainError) as missing:
                await service.effective_tariff(practice_id, on=date(2026, 6, 1))
            assert missing.value.status_code == 404

    run_db(case)


def test_a_plan_from_another_payer_is_rejected():
    async def case(factory):
        async with factory() as setup:
            payer, plan = await build_payer(setup)
            other = Payer(name="Swiss Medical", code="SMG")
            setup.add(other)
            await setup.commit()
            practice_id = (await MedicalPracticeService(setup).create(practice_payload())).id
        async with factory() as session:
            with pytest.raises(DomainError) as invalid:
                await MedicalPracticeService(session).create_tariff(
                    practice_id,
                    MedicalPracticeTariffCreate(
                        payer_id=other.id,
                        health_plan_id=plan.id,
                        unit_value=Decimal(100),
                        valid_from=date(2026, 1, 1),
                    ),
                )
            assert invalid.value.status_code == 422
            assert payer.id != other.id

    run_db(case)


def test_updating_the_units_does_not_rewrite_the_tariffs_already_agreed():
    async def case(factory):
        async with factory() as session:
            practice_id = (await MedicalPracticeService(session).create(practice_payload())).id
        async with factory() as session:
            await MedicalPracticeService(session).create_tariff(
                practice_id,
                MedicalPracticeTariffCreate(unit_value=Decimal(100), valid_from=date(2026, 1, 1)),
            )
        async with factory() as session:
            await MedicalPracticeService(session).update(
                practice_id,
                MedicalPracticeUpdate(**practice_payload(galeno_units=Decimal(60)).model_dump()),
            )
        async with factory() as session:
            tariffs = await MedicalPracticeService(session).list_tariffs(practice_id)
            assert [tariff.total_amount for tariff in tariffs] == [Decimal("5000.00")]

    run_db(case)


def test_deleting_a_practice_takes_its_tariffs_with_it():
    async def case(factory):
        async with factory() as session:
            practice_id = (await MedicalPracticeService(session).create(practice_payload())).id
        async with factory() as session:
            await MedicalPracticeService(session).create_tariff(
                practice_id,
                MedicalPracticeTariffCreate(unit_value=Decimal(100), valid_from=date(2026, 1, 1)),
            )
        async with factory() as session:
            await MedicalPracticeService(session).delete(practice_id)
        async with factory() as session:
            service = MedicalPracticeService(session)
            assert await service.list_practices() == []
            with pytest.raises(DomainError) as missing:
                await service.list_tariffs(practice_id)
            assert missing.value.status_code == 404

    run_db(case)


def test_the_catalog_can_be_filtered_by_nomenclador_chapter_and_text():
    async def case(factory):
        async with factory() as session:
            service = MedicalPracticeService(session)
            await service.create(practice_payload())
            await service.create(
                practice_payload(
                    nomenclador=Nomenclador.NBU,
                    code="66.01.01",
                    name="Hemograma completo",
                    chapter=PracticeChapter.LABORATORIO,
                    practice_type=PracticeType.LABORATORIO,
                    setting=PracticeSetting.AMBOS,
                    galeno_units=Decimal(0),
                    expense_units=Decimal(0),
                    biochemical_units=Decimal(12),
                )
            )
            await service.create(
                practice_payload(
                    code="15.01.02",
                    name="Colecistectomía videolaparoscópica",
                    chapter=PracticeChapter.CIRUGIA,
                    practice_type=PracticeType.CIRUGIA,
                    setting=PracticeSetting.INTERNACION,
                    is_active=False,
                )
            )
        async with factory() as session:
            service = MedicalPracticeService(session)
            assert len(await service.list_practices()) == 3
            assert len(await service.list_practices(nomenclador=Nomenclador.NBU)) == 1
            assert len(await service.list_practices(chapter=PracticeChapter.CIRUGIA)) == 1
            assert len(await service.list_practices(search="hemograma")) == 1
            assert len(await service.list_practices(search="42.01")) == 1
            assert len(await service.list_practices(only_active=True)) == 2
            # A practice for both settings also answers a search by inpatient setting.
            in_hospital = await service.list_practices(setting=PracticeSetting.INTERNACION)
            assert {practice.code for practice in in_hospital} == {"15.01.02", "66.01.01"}

    run_db(case)
