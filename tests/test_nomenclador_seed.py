"""The shipped practice catalog and its loader."""

from decimal import Decimal

from sqlalchemy import func, select

from app.db.seeds.practices import load_catalog, read_catalog
from app.models.practice import MedicalPractice, MedicalPracticeTariff, Nomenclador
from tests.conftest import requires_postgres, run_db


def test_catalog_parses_and_every_code_is_unique_inside_its_nomenclador():
    rows = read_catalog()
    assert rows
    identities = [(row["nomenclador"], row["code"]) for row in rows]
    assert len(set(identities)) == len(identities)
    assert {row["nomenclador"] for row in rows} <= set(Nomenclador)


def test_laboratory_entries_carry_biochemical_units_and_surgeries_carry_galeno():
    rows = {(row["nomenclador"], row["code"]): row for row in read_catalog()}
    lab = rows[(Nomenclador.NBU, "66.01.01")]
    assert lab["biochemical_units"] > 0
    assert lab["galeno_units"] == 0
    surgery = rows[(Nomenclador.NACIONAL, "15.01.02")]
    assert surgery["galeno_units"] > 0
    assert surgery["requires_authorization"] and surgery["requires_consent"]


@requires_postgres
def test_loading_twice_updates_instead_of_duplicating():
    async def case(factory):
        async with factory() as session:
            first = await load_catalog(session)
        async with factory() as session:
            second = await load_catalog(session)
            total = await session.scalar(select(func.count()).select_from(MedicalPractice))
        return first, second, total

    first, second, total = run_db(case)
    assert first.inserted == total
    assert second.inserted == 0
    assert second.updated == total


@requires_postgres
def test_unit_value_prices_the_units_and_leaves_the_modules_unpriced():
    async def case(factory):
        async with factory() as session:
            report = await load_catalog(session, unit_value=Decimal(1000))
            consultation = await session.scalar(
                select(MedicalPractice).where(MedicalPractice.code == "42.01.01")
            )
            tariff = await session.scalar(
                select(MedicalPracticeTariff).where(
                    MedicalPracticeTariff.practice_id == consultation.id
                )
            )
            modules = await session.scalars(
                select(MedicalPractice).where(MedicalPractice.nomenclador == Nomenclador.PROPIO)
            )
            module_tariffs = await session.scalar(
                select(func.count())
                .select_from(MedicalPracticeTariff)
                .where(
                    MedicalPracticeTariff.practice_id.in_([item.id for item in modules.all()])
                )
            )
        return report, tariff, module_tariffs

    report, tariff, module_tariffs = run_db(case)
    assert report.tariffs_created > 0
    # 40 unidades galeno y 10 de gastos, a $1000 la unidad.
    assert tariff.professional_fee == Decimal("40000.00")
    assert tariff.expense_amount == Decimal("10000.00")
    assert tariff.total_amount == Decimal("50000.00")
    assert tariff.payer_id is None
    assert module_tariffs == 0
