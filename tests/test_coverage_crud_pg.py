"""CRUD of the coverage catalog: payers, plans and the coverages a patient holds."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.models.coverage import CoverageStatus
from app.models.patient import Patient
from app.models.practice import (
    MedicalPractice,
    MedicalPracticeTariff,
    Nomenclador,
    PracticeChapter,
    PracticeType,
)
from app.schemas.domain import PatientCoverageCreate, PatientCoverageUpdate
from app.schemas.workflow import HealthPlanCreate, HealthPlanUpdate, PayerCreate, PayerUpdate
from app.services.registry import CoverageService
from tests.conftest import requires_postgres, run_db

pytestmark = requires_postgres


async def build_patient(session) -> Patient:
    patient = Patient(
        first_name="Ana",
        last_name="Gomez",
        document_type="DNI",
        document_number="30111222",
    )
    session.add(patient)
    await session.commit()
    return patient


def test_payer_is_created_read_updated_and_deleted():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            found = await service.get_payer(payer.id)
            renamed = await service.update_payer(
                payer.id,
                PayerUpdate(name="OSDE Binario", code="OSDE", tax_id="30-54666577-0"),
            )
            await service.delete_payer(payer.id)
            remaining = await service.list_payers()
            return found.code, renamed.name, renamed.tax_id, remaining

    code, name, tax_id, remaining = run_db(case)
    assert code == "OSDE"
    assert name == "OSDE Binario"
    assert tax_id == "30-54666577-0"
    assert remaining == []


def test_payer_code_is_unique():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            with pytest.raises(DomainError) as excinfo:
                await service.create_payer(PayerCreate(name="Otra", code="OSDE"))
            return excinfo.value.status_code

    assert run_db(case) == 409


def test_payers_are_searched_by_name_or_code():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            await service.create_payer(PayerCreate(name="Swiss Medical", code="SMG"))
            by_name = await service.list_payers(search="swiss")
            by_code = await service.list_payers(search="OSD")
            return [payer.code for payer in by_name], [payer.code for payer in by_code]

    by_name, by_code = run_db(case)
    assert by_name == ["SMG"]
    assert by_code == ["OSDE"]


def test_a_payer_with_plans_cannot_be_deleted():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            await service.create_health_plan(payer.id, HealthPlanCreate(name="210", code="210"))
            with pytest.raises(DomainError) as excinfo:
                await service.delete_payer(payer.id)
            return excinfo.value.status_code, excinfo.value.message

    status_code, message = run_db(case)
    assert status_code == 409
    assert "planes" in message


def test_a_payer_with_agreed_tariffs_cannot_be_deleted():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            practice = MedicalPractice(
                nomenclador=Nomenclador.NACIONAL,
                code="42.01.01",
                name="Consulta en consultorio",
                chapter=PracticeChapter.CONSULTAS,
                practice_type=PracticeType.CONSULTA,
            )
            session.add(practice)
            await session.flush()
            session.add(
                MedicalPracticeTariff(
                    practice_id=practice.id,
                    payer_id=payer.id,
                    total_amount=Decimal("1000.00"),
                    valid_from=date(2026, 1, 1),
                )
            )
            await session.commit()
            with pytest.raises(DomainError) as excinfo:
                await service.delete_payer(payer.id)
            return excinfo.value.message

    assert "aranceles" in run_db(case)


def test_plan_is_listed_by_payer_updated_and_deleted():
    # A session per step, like the API: each request opens and closes its own.
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            other = await service.create_payer(PayerCreate(name="Swiss", code="SMG"))
            plan = await service.create_health_plan(
                payer.id, HealthPlanCreate(name="210", code="210")
            )
            await service.create_health_plan(other.id, HealthPlanCreate(name="SMG20", code="SMG20"))
            renamed = await service.update_health_plan(
                plan.id, HealthPlanUpdate(name="Plan 210", code="210")
            )
            payer_id, plan_id = payer.id, plan.id
            name, kept_payer = renamed.name, renamed.payer_id == payer_id
        async with factory() as session:
            service = CoverageService(session)
            of_payer = await service.list_health_plans(payer_id)
            every = await service.list_health_plans()
        async with factory() as session:
            await CoverageService(session).delete_health_plan(plan_id)
        async with factory() as session:
            left = await CoverageService(session).list_health_plans(payer_id)
        return name, kept_payer, len(of_payer), len(every), left

    name, kept_payer, of_payer, every, left = run_db(case)
    assert name == "Plan 210"
    assert kept_payer
    assert (of_payer, every) == (1, 2)
    assert left == []


def test_plan_code_is_unique_inside_the_payer_but_not_across_payers():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            other = await service.create_payer(PayerCreate(name="Swiss", code="SMG"))
            await service.create_health_plan(payer.id, HealthPlanCreate(name="210", code="210"))
            reused = await service.create_health_plan(
                other.id, HealthPlanCreate(name="210", code="210")
            )
            reused_id = reused.id
            with pytest.raises(DomainError) as excinfo:
                await service.create_health_plan(
                    payer.id, HealthPlanCreate(name="Duplicado", code="210")
                )
            return reused_id is not None, excinfo.value.status_code

    reused, status_code = run_db(case)
    assert reused
    assert status_code == 409


def test_coverage_snapshots_the_payer_and_plan_names():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            patient = await build_patient(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            plan = await service.create_health_plan(
                payer.id, HealthPlanCreate(name="210", code="210")
            )
            coverage = await service.create_coverage(
                patient.id,
                PatientCoverageCreate(health_plan_id=plan.id, member_number="6120"),
            )
            return coverage.payer_id == payer.id, coverage.payer_name, coverage.plan_name

    resolved_payer, payer_name, plan_name = run_db(case)
    assert resolved_payer
    assert (payer_name, plan_name) == ("OSDE", "210")


def test_updating_a_coverage_rereads_the_catalog():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            patient = await build_patient(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            other = await service.create_payer(PayerCreate(name="Swiss Medical", code="SMG"))
            plan = await service.create_health_plan(
                other.id, HealthPlanCreate(name="SMG20", code="SMG20")
            )
            coverage = await service.create_coverage(
                patient.id, PatientCoverageCreate(payer_id=payer.id, member_number="6120")
            )
            moved = await service.update_coverage(
                coverage.id,
                PatientCoverageUpdate(
                    health_plan_id=plan.id,
                    member_number="7788",
                    status=CoverageStatus.INACTIVE,
                ),
            )
            return moved.payer_id == other.id, moved.payer_name, moved.plan_name, moved.status

    moved_payer, payer_name, plan_name, status = run_db(case)
    assert moved_payer
    assert (payer_name, plan_name) == ("Swiss Medical", "SMG20")
    assert status is CoverageStatus.INACTIVE


def test_a_coverage_cannot_be_moved_to_a_plan_of_another_payer():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            patient = await build_patient(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            other = await service.create_payer(PayerCreate(name="Swiss", code="SMG"))
            plan = await service.create_health_plan(
                other.id, HealthPlanCreate(name="SMG20", code="SMG20")
            )
            coverage = await service.create_coverage(
                patient.id, PatientCoverageCreate(payer_id=payer.id)
            )
            with pytest.raises(DomainError) as excinfo:
                await service.update_coverage(
                    coverage.id,
                    PatientCoverageUpdate(payer_id=payer.id, health_plan_id=plan.id),
                )
            return excinfo.value.status_code

    assert run_db(case) == 422


def test_an_invalid_period_is_rejected():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            patient = await build_patient(session)
            with pytest.raises(DomainError) as excinfo:
                await service.create_coverage(
                    patient.id,
                    PatientCoverageCreate(
                        payer_name="Particular",
                        valid_from=date(2026, 5, 1),
                        valid_until=date(2026, 4, 1),
                    ),
                )
            return excinfo.value.status_code

    assert run_db(case) == 422


def test_coverage_is_deleted_and_the_plan_behind_it_is_protected_while_in_use():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            patient = await build_patient(session)
            payer = await service.create_payer(PayerCreate(name="OSDE", code="OSDE"))
            plan = await service.create_health_plan(
                payer.id, HealthPlanCreate(name="210", code="210")
            )
            coverage = await service.create_coverage(
                patient.id, PatientCoverageCreate(health_plan_id=plan.id)
            )
            patient_id, plan_id, coverage_id = patient.id, plan.id, coverage.id
            with pytest.raises(DomainError) as excinfo:
                await service.delete_health_plan(plan_id)
            message = excinfo.value.message
        async with factory() as session:
            service = CoverageService(session)
            await service.delete_coverage(coverage_id)
        async with factory() as session:
            service = CoverageService(session)
            await service.delete_health_plan(plan_id)
        async with factory() as session:
            coverages = await CoverageService(session).list_coverages(patient_id)
        return message, coverages

    message, coverages = run_db(case)
    assert "coberturas" in message
    assert coverages == []


def test_unknown_ids_answer_404():
    async def case(factory):
        async with factory() as session:
            service = CoverageService(session)
            unknown = uuid.uuid4()
            codes = []
            for call in (
                lambda: service.get_payer(unknown),
                lambda: service.get_health_plan(unknown),
                lambda: service.get_coverage(unknown),
                lambda: service.list_coverages(unknown),
                lambda: service.list_health_plans(unknown),
            ):
                with pytest.raises(DomainError) as excinfo:
                    await call()
                codes.append(excinfo.value.status_code)
            return codes

    assert run_db(case) == [404] * 5
