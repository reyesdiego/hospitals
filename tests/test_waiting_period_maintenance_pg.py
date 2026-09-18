"""El script que pasa las carencias pactadas de la cartilla a la carencia de la práctica."""

import uuid

import pytest
from sqlalchemy import select

from app.db.maintenance.waiting_periods import inherit_waiting_periods
from app.models.practice import (
    HealthPlanPractice,
    MedicalPractice,
    Nomenclador,
    PracticeChapter,
    PracticeType,
)
from app.schemas.practice import HealthPlanPracticeCreate
from app.schemas.workflow import HealthPlanCreate, PayerCreate
from app.services.plan_coverage import HealthPlanPracticeService
from app.services.registry import CoverageService
from tests.conftest import requires_postgres, run_db

pytestmark = requires_postgres


async def build_cartilla(session) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Un plan con tres prácticas: dos con carencia 0 pactada y una con 30."""

    coverage = CoverageService(session)
    payer = await coverage.create_payer(PayerCreate(name="OMINT", code="OMINT"))
    plan = await coverage.create_health_plan(payer.id, HealthPlanCreate(name="4500", code="4500"))

    practices = {
        "42.01.01": 0,
        "15.01.02": 180,
        "34.07.01": 90,
    }
    ids: dict[str, uuid.UUID] = {}
    for code, default_waiting in practices.items():
        practice = MedicalPractice(
            nomenclador=Nomenclador.NACIONAL,
            code=code,
            name=f"Practica {code}",
            chapter=PracticeChapter.CONSULTAS,
            practice_type=PracticeType.CONSULTA,
            default_waiting_period_days=default_waiting,
        )
        session.add(practice)
        await session.flush()
        ids[code] = practice.id
    await session.commit()

    service = HealthPlanPracticeService(session)
    for code in ("42.01.01", "15.01.02"):
        await service.link(
            plan.id,
            HealthPlanPracticeCreate(practice_id=ids[code], waiting_period_days=0),
        )
    await service.link(
        plan.id,
        HealthPlanPracticeCreate(practice_id=ids["34.07.01"], waiting_period_days=30),
    )
    return plan.id, ids


async def agreed_values(session, plan_id) -> dict[str, int | None]:
    rows = (
        await session.execute(
            select(MedicalPractice.code, HealthPlanPractice.waiting_period_days)
            .join(HealthPlanPractice, HealthPlanPractice.practice_id == MedicalPractice.id)
            .where(HealthPlanPractice.health_plan_id == plan_id)
        )
    ).all()
    return {code: waiting for code, waiting in rows}


def test_by_default_it_only_reports_and_changes_nothing():
    async def case(factory):
        async with factory() as session:
            plan_id, _ = await build_cartilla(session)
        async with factory() as session:
            report = await inherit_waiting_periods(session)
            return report, await agreed_values(session, plan_id)

    report, values = run_db(case)
    assert not report.applied
    assert len(report.rows) == 2  # las dos que tienen 0 pactado
    assert values == {"42.01.01": 0, "15.01.02": 0, "34.07.01": 30}


def test_applying_it_leaves_the_zeros_inheriting_and_respects_the_agreed_ones():
    async def case(factory):
        async with factory() as session:
            plan_id, _ = await build_cartilla(session)
        async with factory() as session:
            report = await inherit_waiting_periods(session, apply=True)
        async with factory() as session:
            return report, await agreed_values(session, plan_id)

    report, values = run_db(case)
    assert report.applied
    # La cirugía pasa a heredar los 180 de la práctica; la resonancia mantiene sus 30.
    assert values == {"42.01.01": None, "15.01.02": None, "34.07.01": 30}


def test_any_takes_the_agreed_values_too_and_plan_limits_the_scope():
    async def case(factory):
        async with factory() as session:
            plan_id, _ = await build_cartilla(session)
        async with factory() as session:
            await inherit_waiting_periods(session, health_plan_id=plan_id, only_value=None, apply=True)
        async with factory() as session:
            return await agreed_values(session, plan_id)

    assert run_db(case) == {"42.01.01": None, "15.01.02": None, "34.07.01": None}


def test_an_unknown_plan_is_rejected():
    async def case(factory):
        async with factory() as session:
            await build_cartilla(session)
        async with factory() as session:
            with pytest.raises(ValueError):
                await inherit_waiting_periods(session, health_plan_id=uuid.uuid4())
            return True

    assert run_db(case)


def test_the_report_shows_what_each_practice_would_inherit():
    async def case(factory):
        async with factory() as session:
            await build_cartilla(session)
        async with factory() as session:
            report = await inherit_waiting_periods(session)
            return {row.practice_code: (row.agreed, row.inherited) for row in report.rows}, str(
                report
            )

    rows, text = run_db(case)
    assert rows == {"42.01.01": (0, 0), "15.01.02": (0, 180)}
    assert "1 cambian de valor" in text
    assert "--apply" in text
