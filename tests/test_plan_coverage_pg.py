"""Cartilla de un plan: qué prácticas cubre y en qué condiciones."""

import uuid
from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.models.practice import (
    MedicalPractice,
    Nomenclador,
    PracticeChapter,
    PracticeType,
)
from app.schemas.practice import (
    HealthPlanPracticeBulkCreate,
    HealthPlanPracticeCreate,
    HealthPlanPracticeUpdate,
)
from app.schemas.workflow import HealthPlanCreate, PayerCreate
from app.services.plan_coverage import HealthPlanPracticeService, effective_waiting_period
from app.services.registry import CoverageService
from tests.conftest import requires_postgres, run_db

pytestmark = requires_postgres


async def build_plan_and_practices(session) -> tuple[uuid.UUID, list[MedicalPractice]]:
    coverage = CoverageService(session)
    payer = await coverage.create_payer(PayerCreate(name="OSDE", code="OSDE"))
    plan = await coverage.create_health_plan(payer.id, HealthPlanCreate(name="210", code="210"))
    practices = [
        MedicalPractice(
            nomenclador=Nomenclador.NACIONAL,
            code="42.01.01",
            name="Consulta en consultorio",
            chapter=PracticeChapter.CONSULTAS,
            practice_type=PracticeType.CONSULTA,
        ),
        MedicalPractice(
            nomenclador=Nomenclador.NACIONAL,
            code="34.07.01",
            name="Resonancia magnetica de cerebro",
            chapter=PracticeChapter.DIAGNOSTICO_POR_IMAGENES,
            practice_type=PracticeType.IMAGENES,
            requires_authorization=True,
        ),
        MedicalPractice(
            nomenclador=Nomenclador.NBU,
            code="66.01.01",
            name="Hemograma completo",
            chapter=PracticeChapter.LABORATORIO,
            practice_type=PracticeType.LABORATORIO,
        ),
    ]
    session.add_all(practices)
    await session.commit()
    return plan.id, practices


def test_a_practice_is_linked_with_its_conditions():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            entry = await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(
                    practice_id=practices[1].id,
                    waiting_period_days=90,
                    copayment_amount=Decimal("4500.00"),
                    requires_authorization=True,
                ),
            )
            return (
                entry.practice.code,
                entry.waiting_period_days,
                entry.copayment_amount,
                entry.requires_authorization,
                entry.is_covered,
            )

    code, waiting, copayment, authorization, covered = run_db(case)
    assert code == "34.07.01"
    assert waiting == 90
    assert copayment == Decimal("4500.00")
    assert authorization
    assert covered


def test_the_same_practice_cannot_be_linked_twice_to_a_plan():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            service = HealthPlanPracticeService(session)
            await service.link(plan_id, HealthPlanPracticeCreate(practice_id=practices[0].id))
            with pytest.raises(DomainError) as excinfo:
                await service.link(plan_id, HealthPlanPracticeCreate(practice_id=practices[0].id))
            return excinfo.value.status_code

    assert run_db(case) == 409


def test_a_practice_is_deactivated_without_losing_the_row():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            service = HealthPlanPracticeService(session)
            entry = await service.link(
                plan_id, HealthPlanPracticeCreate(practice_id=practices[0].id)
            )
            excluded = await service.update(
                plan_id,
                entry.id,
                HealthPlanPracticeUpdate(is_covered=False, notes="Fuera de cartilla 2026"),
            )
            listed = await service.list_practices(plan_id)
            covered_only = await service.list_practices(plan_id, only_covered=True)
            return excluded.is_covered, excluded.notes, len(listed), len(covered_only)

    is_covered, notes, listed, covered_only = run_db(case)
    assert is_covered is False
    assert notes == "Fuera de cartilla 2026"
    assert (listed, covered_only) == (1, 0)


def test_bulk_link_skips_what_is_already_in_the_cartilla():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            service = HealthPlanPracticeService(session)
            first = await service.link(
                plan_id,
                HealthPlanPracticeCreate(
                    practice_id=practices[0].id, copayment_amount=Decimal("1000.00")
                ),
            )
            created, skipped = await service.link_many(
                plan_id,
                HealthPlanPracticeBulkCreate(
                    practice_ids=[practice.id for practice in practices],
                    waiting_period_days=30,
                    copayment_amount=Decimal("2500.00"),
                ),
            )
            untouched = await service.get(plan_id, first.id)
            return (
                sorted(entry.practice.code for entry in created),
                skipped == [practices[0].id],
                untouched.copayment_amount,
                created[0].waiting_period_days,
            )

    codes, skipped_first, untouched_copayment, waiting = run_db(case)
    assert codes == ["34.07.01", "66.01.01"]
    assert skipped_first
    assert untouched_copayment == Decimal("1000.00")
    assert waiting == 30


def test_the_cartilla_is_filtered_by_chapter_and_text():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            service = HealthPlanPracticeService(session)
            await service.link_many(
                plan_id,
                HealthPlanPracticeBulkCreate(
                    practice_ids=[practice.id for practice in practices]
                ),
            )
            by_chapter = await service.list_practices(
                plan_id, chapter=PracticeChapter.LABORATORIO
            )
            by_text = await service.list_practices(plan_id, search="resonancia")
            by_code = await service.list_practices(plan_id, search="42.01")
            return (
                [entry.practice.code for entry in by_chapter],
                [entry.practice.code for entry in by_text],
                [entry.practice.code for entry in by_code],
            )

    by_chapter, by_text, by_code = run_db(case)
    assert by_chapter == ["66.01.01"]
    assert by_text == ["34.07.01"]
    assert by_code == ["42.01.01"]


def test_the_plan_requirement_is_independent_from_the_one_of_the_nomenclador():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            # La consulta no exige autorización en el nomenclador, pero este plan sí.
            entry = await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(
                    practice_id=practices[0].id, requires_authorization=True
                ),
            )
            return entry.practice.requires_authorization, entry.requires_authorization

    catalog, plan = run_db(case)
    assert catalog is False
    assert plan is True


def test_unlinking_leaves_the_practice_in_the_catalog():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            service = HealthPlanPracticeService(session)
            entry = await service.link(
                plan_id, HealthPlanPracticeCreate(practice_id=practices[0].id)
            )
            await service.unlink(plan_id, entry.id)
            remaining = await service.list_practices(plan_id)
            still_in_catalog = await session.get(MedicalPractice, practices[0].id)
            return remaining, still_in_catalog is not None

    remaining, in_catalog = run_db(case)
    assert remaining == []
    assert in_catalog


def test_unknown_plan_practice_or_entry_answer_404():
    # A session per call: a read leaves a transaction open and the next write cannot begin.
    async def case(factory):
        async with factory() as session:
            plan_id, _ = await build_plan_and_practices(session)
        unknown = uuid.uuid4()
        calls = [
            lambda service: service.list_practices(unknown),
            lambda service: service.link(unknown, HealthPlanPracticeCreate(practice_id=unknown)),
            lambda service: service.link(plan_id, HealthPlanPracticeCreate(practice_id=unknown)),
            lambda service: service.get(plan_id, unknown),
            lambda service: service.link_many(
                plan_id, HealthPlanPracticeBulkCreate(practice_ids=[unknown])
            ),
        ]
        codes = []
        for call in calls:
            async with factory() as session:
                with pytest.raises(DomainError) as excinfo:
                    await call(HealthPlanPracticeService(session))
                codes.append(excinfo.value.status_code)
        return codes

    assert run_db(case) == [404] * 5


def test_bulk_link_returns_rows_readable_outside_the_session_that_created_them():
    """Regresión: el alta masiva devolvía filas con la práctica sin cargar, y el presenter
    de la API la pedía fuera del contexto async, después de haber guardado."""

    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            practice_ids = [practice.id for practice in practices]
        # Sesión nueva, como la de un request: ninguna práctica está en el identity map.
        async with factory() as session:
            created, _ = await HealthPlanPracticeService(session).link_many(
                plan_id, HealthPlanPracticeBulkCreate(practice_ids=practice_ids)
            )
            return sorted(entry.practice.code for entry in created)

    assert run_db(case) == ["34.07.01", "42.01.01", "66.01.01"]


def test_a_single_link_is_also_readable_with_its_practice():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            practice_id = practices[0].id
        async with factory() as session:
            entry = await HealthPlanPracticeService(session).link(
                plan_id, HealthPlanPracticeCreate(practice_id=practice_id)
            )
            return entry.practice.code

    assert run_db(case) == "42.01.01"


def test_the_practice_lends_its_waiting_period_to_the_plan_that_does_not_set_one():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            surgery = practices[1]
            surgery.default_waiting_period_days = 180
            await session.commit()
            surgery_id = surgery.id
        async with factory() as session:
            service = HealthPlanPracticeService(session)
            inherited = await service.link(
                plan_id, HealthPlanPracticeCreate(practice_id=surgery_id)
            )
            return (
                inherited.waiting_period_days,
                inherited.practice.default_waiting_period_days,
            )

    plan_value, practice_value = run_db(case)
    # La cartilla no guarda nada propio: la carencia sigue siendo la de la práctica.
    assert plan_value is None
    assert practice_value == 180


def test_the_plan_can_agree_its_own_waiting_period_and_go_back_to_the_default():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            surgery = practices[1]
            surgery.default_waiting_period_days = 180
            await session.commit()
            surgery_id = surgery.id
        async with factory() as session:
            entry = await HealthPlanPracticeService(session).link(
                plan_id,
                HealthPlanPracticeCreate(practice_id=surgery_id, waiting_period_days=30),
            )
            entry_id, agreed = entry.id, entry.waiting_period_days
        async with factory() as session:
            back = await HealthPlanPracticeService(session).update(
                plan_id, entry_id, HealthPlanPracticeUpdate(waiting_period_days=None)
            )
            return agreed, back.waiting_period_days

    agreed, back = run_db(case)
    assert agreed == 30
    assert back is None


def test_the_effective_waiting_period_is_the_one_of_the_plan_when_it_agreed_one():
    async def case(factory):
        async with factory() as session:
            plan_id, practices = await build_plan_and_practices(session)
            surgery = practices[1]
            surgery.default_waiting_period_days = 180
            await session.commit()
            surgery_id, consult_id = surgery.id, practices[0].id
        async with factory() as session:
            service = HealthPlanPracticeService(session)
            await service.link(
                plan_id,
                HealthPlanPracticeCreate(practice_id=surgery_id, waiting_period_days=30),
            )
            await service.link(plan_id, HealthPlanPracticeCreate(practice_id=consult_id))
        async with factory() as session:
            entries = await HealthPlanPracticeService(session).list_practices(plan_id)
            return {
                entry.practice.code: effective_waiting_period(entry, entry.practice)
                for entry in entries
            }

    effective = run_db(case)
    # La resonancia tiene 180 de carencia en el nomenclador, pero este plan pactó 30.
    assert effective["34.07.01"] == 30
    assert effective["42.01.01"] == 0
