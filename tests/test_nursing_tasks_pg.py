"""Panel de enfermería: lo que el médico indica y enfermería ejecuta."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import DomainError
from app.core.permissions import Permission, UserRole, permissions_of
from app.core.users import RequestUser
from app.models.practice import (
    Nomenclador,
    PracticeChapter,
    PracticeOrderStatus,
    PracticeType,
)
from app.schemas.practice import (
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticeCreate,
    HospitalizationPracticePerformCreate,
    MedicalPracticeCreate,
    MedicalPracticeTariffCreate,
)
from app.services.account import AccountService
from app.services.bed_assignment import BedAssignmentService
from app.services.nursing import NursingTaskService, today_local
from app.services.practice import HospitalizationPracticeService, MedicalPracticeService
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

NURSE = RequestUser(role="NURSE", name="Enf. Perez")
PRESCRIBED_AT = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)


async def catalog_practice(session, *, code: str, name: str, nursing: bool):
    service = MedicalPracticeService(session)
    practice = await service.create(
        MedicalPracticeCreate(
            nomenclador=Nomenclador.NACIONAL,
            code=code,
            name=name,
            chapter=PracticeChapter.PRACTICAS_ESPECIALIZADAS,
            practice_type=PracticeType.PRACTICA,
            galeno_units=Decimal(10),
            expense_units=Decimal(5),
            is_nursing_task=nursing,
        )
    )
    await service.create_tariff(
        practice.id,
        MedicalPracticeTariffCreate(unit_value=Decimal(100), valid_from=date(2026, 1, 1)),
    )
    return practice


async def admitted(factory, scenario):
    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    return hospitalization_id


async def prescribe(factory, hospitalization_id, scenario, practice_id, **overrides):
    data = {
        "practice_id": practice_id,
        "prescribed_by_id": scenario.practitioner_id,
        "prescribed_at": PRESCRIBED_AT,
    }
    data.update(overrides)
    async with factory() as session:
        order = await HospitalizationPracticeService(session).register(
            hospitalization_id, HospitalizationPracticeCreate(**data)
        )
        return order.id


def test_nursing_sees_what_the_doctor_indicated_with_the_patient_and_the_bed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted(factory, scenario)
        async with factory() as session:
            injection = await catalog_practice(
                session, code="19.01.01", name="Inyeccion intramuscular", nursing=True
            )
            surgery = await catalog_practice(
                session, code="15.01.01", name="Apendicectomia", nursing=False
            )
            injection_id, surgery_id = injection.id, surgery.id
        await prescribe(factory, hospitalization_id, scenario, injection_id)
        await prescribe(factory, hospitalization_id, scenario, surgery_id)
        async with factory() as session:
            tasks = await NursingTaskService(session).worklist()
            return [
                (
                    task.order.practice_code,
                    task.patient.last_name,
                    task.bed_code is not None,
                    task.prescribed_by is not None,
                )
                for task in tasks
            ]

    tasks = run_db(case)
    # Solo la tarea de enfermería: la cirugía la registra quien la hace.
    assert len(tasks) == 1
    code, _, has_bed, has_prescriber = tasks[0]
    assert code == "19.01.01"
    assert has_bed and has_prescriber


def test_marking_it_applied_charges_the_account_like_any_practice():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(
                session, code="19.03.01", name="Extraccion de sangre", nursing=True
            )
            practice_id = practice.id
        order_id = await prescribe(factory, hospitalization_id, scenario, practice_id)
        async with factory() as session:
            applied = await NursingTaskService(session, NURSE).perform(
                order_id,
                HospitalizationPracticePerformCreate(recorded_by="Enf. Perez"),
            )
            status = applied.status
        async with factory() as session:
            account = await AccountService(session).for_hospitalization(hospitalization_id)
            charges = [(item.description, item.amount) for item in account.charge_items]
        async with factory() as session:
            pending = await NursingTaskService(session).worklist()
        return status, charges, pending

    status, charges, pending = run_db(case)
    assert status is PracticeOrderStatus.PERFORMED
    assert charges == [("19.03.01 - Extraccion de sangre", Decimal("1500.00"))]
    assert pending == []  # deja de estar pendiente


def test_a_task_can_be_cancelled_with_its_reason():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(
                session, code="19.04.01", name="Colocacion de Holter", nursing=True
            )
            practice_id = practice.id
        order_id = await prescribe(factory, hospitalization_id, scenario, practice_id)
        async with factory() as session:
            cancelled = await NursingTaskService(session, NURSE).cancel(
                order_id,
                HospitalizationPracticeCancelCreate(
                    reason="El paciente bajó a estudios", actor="Enf. Perez"
                ),
            )
            return cancelled.status, cancelled.notes, cancelled.cancelled_at is not None

    status, notes, has_timestamp = run_db(case)
    assert status is PracticeOrderStatus.CANCELLED
    assert notes == "El paciente bajó a estudios"
    assert has_timestamp


def test_a_practice_that_is_not_a_nursing_task_does_not_go_through_this_panel():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(
                session, code="34.07.01", name="Resonancia", nursing=False
            )
            practice_id = practice.id
        order_id = await prescribe(factory, hospitalization_id, scenario, practice_id)
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await NursingTaskService(session, NURSE).perform(
                    order_id, HospitalizationPracticePerformCreate()
                )
            return excinfo.value.status_code, excinfo.value.message

    status_code, message = run_db(case)
    assert status_code == 409
    assert "no es una tarea de enfermería" in message


def test_the_day_is_the_one_of_the_hospital_and_not_the_one_of_utc():
    """De noche, UTC ya está en el día siguiente: el turno dejaría de ver lo que aplicó."""

    from zoneinfo import ZoneInfo

    from app.core.config import settings
    from app.services.nursing import _happened_on

    hospital = ZoneInfo(settings.timezone)
    order = SimpleNamespace(
        performed_at=datetime(2026, 9, 20, 1, 30, tzinfo=UTC),  # 22:30 del 19 en el hospital
        cancelled_at=None,
        prescribed_at=datetime(2026, 9, 19, 20, 0, tzinfo=UTC),
    )

    assert order.performed_at.astimezone(hospital).date() == date(2026, 9, 19)
    assert _happened_on(order, date(2026, 9, 19))
    assert not _happened_on(order, date(2026, 9, 20))


def test_the_worklist_can_show_what_was_resolved_during_the_shift():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(
                session, code="19.05.02", name="Control de signos vitales", nursing=True
            )
            practice_id = practice.id
        done_id = await prescribe(factory, hospitalization_id, scenario, practice_id)
        async with factory() as session:
            await NursingTaskService(session, NURSE).perform(
                done_id, HospitalizationPracticePerformCreate()
            )
        async with factory() as session:
            pending = await NursingTaskService(session).worklist()
            today = await NursingTaskService(session).worklist(
                pending_only=False, on=today_local()
            )
            other_day = await NursingTaskService(session).worklist(
                pending_only=False, on=date(2020, 1, 1)
            )
        return len(pending), len(today), len(other_day)

    pending, today, other_day = run_db(case)
    assert pending == 0
    assert today == 1
    assert other_day == 0


def test_an_unknown_task_is_404():
    async def case(factory):
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await NursingTaskService(session, NURSE).perform(
                    uuid.uuid4(), HospitalizationPracticePerformCreate()
                )
            return excinfo.value.status_code

    assert run_db(case) == 404


def test_nursing_has_the_permission_and_reception_does_not():
    assert Permission.NURSING_TASKS in permissions_of(UserRole.NURSE)
    assert Permission.NURSING_TASKS in permissions_of(UserRole.ADMIN)
    assert Permission.NURSING_TASKS not in permissions_of(UserRole.RECEPTIONIST)
    assert Permission.NURSING_TASKS not in permissions_of(UserRole.DOCTOR)


def test_the_practice_records_which_nurse_applied_it():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(
                session, code="19.01.02", name="Inyeccion subcutanea", nursing=True
            )
            practice_id = practice.id
        order_id = await prescribe(factory, hospitalization_id, scenario, practice_id)
        async with factory() as session:
            applied = await NursingTaskService(session, NURSE).perform(
                order_id, HospitalizationPracticePerformCreate()
            )
            return applied.performed_by_user_name, applied.performed_by_id
        # El profesional ejecutor queda vacío: quien la aplicó es la enfermera, que no está
        # en el padrón de profesionales.

    performed_by, professional = run_db(case)
    assert performed_by == "Enf. Perez"
    assert professional is None


def test_the_worklist_shows_who_applied_each_task():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(
                session, code="19.05.03", name="Control de glucemia", nursing=True
            )
            practice_id = practice.id
        order_id = await prescribe(factory, hospitalization_id, scenario, practice_id)
        async with factory() as session:
            await NursingTaskService(session, NURSE).perform(
                order_id, HospitalizationPracticePerformCreate()
            )
        async with factory() as session:
            tasks = await NursingTaskService(session).worklist(
                pending_only=False, on=today_local()
            )
            return [task.order.performed_by_user_name for task in tasks]

    assert run_db(case) == ["Enf. Perez"]
