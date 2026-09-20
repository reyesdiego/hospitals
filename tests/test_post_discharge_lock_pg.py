"""Con el alta médica dada la internación deja de recibir cambios, salvo de un administrador."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.core.users import STAFF, RequestUser
from app.models.audit import HospitalizationEventType
from app.models.practice import Nomenclador, PracticeChapter, PracticeType
from app.schemas.practice import (
    HospitalizationPracticeCreate,
    MedicalPracticeCreate,
    MedicalPracticeTariffCreate,
)
from app.schemas.workflow import (
    ChargeItemCreate,
    ChargeItemVoidCreate,
    ClinicalDischargeCreate,
    PhysicalDepartureCreate,
)
from app.services.account import AccountService
from app.services.audit import list_events
from app.services.bed_assignment import BedAssignmentService
from app.services.hospitalization import HospitalizationService
from app.services.practice import HospitalizationPracticeService, MedicalPracticeService
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

ADMIN = RequestUser(role="admin", name="Ana Supervisora")
PERFORMED_AT = datetime(2026, 6, 1, 10, 30, tzinfo=UTC)


async def catalog_practice(session):
    service = MedicalPracticeService(session)
    practice = await service.create(
        MedicalPracticeCreate(
            nomenclador=Nomenclador.NACIONAL,
            code="42.01.01",
            name="Consulta en consultorio",
            chapter=PracticeChapter.CONSULTAS,
            practice_type=PracticeType.CONSULTA,
            galeno_units=Decimal(40),
            expense_units=Decimal(10),
        )
    )
    await service.create_tariff(
        practice.id,
        MedicalPracticeTariffCreate(unit_value=Decimal(100), valid_from=date(2026, 1, 1)),
    )
    return practice


async def discharged_hospitalization(factory, scenario):
    """Internación con el paciente en cama y el alta médica ya firmada."""

    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    async with factory() as session:
        await HospitalizationService(session).clinical_discharge(
            hospitalization_id,
            ClinicalDischargeCreate(discharge_reason="Evolución favorable"),
        )
    return hospitalization_id


def charge_payload(**overrides) -> ChargeItemCreate:
    data: dict = {
        "category": "MEDICATION",
        "description": "Analgésico",
        "quantity": Decimal(1),
        "unit_price": Decimal("1500.00"),
    }
    data.update(overrides)
    return ChargeItemCreate(**data)


def test_staff_cannot_add_a_practice_after_the_medical_discharge():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged_hospitalization(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await HospitalizationPracticeService(session, STAFF).register(
                    hospitalization_id,
                    HospitalizationPracticeCreate(
                        practice_id=practice.id,
                        prescribed_by_id=scenario.practitioner_id,
                        performed_at=PERFORMED_AT,
                    ),
                )
            return excinfo.value.status_code, excinfo.value.message

    status_code, message = run_db(case)
    assert status_code == 403
    assert "solo un administrador" in message


def test_an_admin_can_and_the_change_is_recorded_in_the_history():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged_hospitalization(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session, ADMIN).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            status = order.status.value
        async with factory() as session:
            events = await list_events(session, hospitalization_id)
        overrides = [
            event
            for event in events
            if event.event_type is HospitalizationEventType.POST_DISCHARGE_CHANGE
        ]
        return status, [(event.actor, (event.details or {}).get("action")) for event in overrides]

    status, overrides = run_db(case)
    assert status == "PERFORMED"
    assert overrides == [("Ana Supervisora", "Indicar una práctica")]


def test_the_account_is_also_locked_and_the_admin_can_still_correct_it():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged_hospitalization(factory, scenario)
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AccountService(session, STAFF).add_charge_item(
                    hospitalization_id, charge_payload()
                )
            blocked = excinfo.value.status_code
        async with factory() as session:
            item = await AccountService(session, ADMIN).add_charge_item(
                hospitalization_id, charge_payload()
            )
            item_id = item.id
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AccountService(session, STAFF).void_charge_item(
                    hospitalization_id, item_id, ChargeItemVoidCreate(reason="Error")
                )
            void_blocked = excinfo.value.status_code
        async with factory() as session:
            voided = await AccountService(session, ADMIN).void_charge_item(
                hospitalization_id, item_id, ChargeItemVoidCreate(reason="Error de carga")
            )
            return blocked, void_blocked, voided.status.value

    blocked, void_blocked, voided = run_db(case)
    assert blocked == 403
    assert void_blocked == 403
    assert voided == "VOID"


def test_before_the_medical_discharge_nothing_changes_for_the_staff():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            order = await HospitalizationPracticeService(session, STAFF).register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice.id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at=PERFORMED_AT,
                ),
            )
            status = order.status.value
        async with factory() as session:
            item = await AccountService(session, STAFF).add_charge_item(
                hospitalization_id, charge_payload()
            )
        async with factory() as session:
            events = await list_events(session, hospitalization_id)
        return (
            status,
            item.amount,
            any(
                event.event_type is HospitalizationEventType.POST_DISCHARGE_CHANGE
                for event in events
            ),
        )

    status, amount, recorded = run_db(case)
    assert status == "PERFORMED"
    assert amount == Decimal("1500.00")
    assert not recorded


def test_the_lock_stays_after_the_administrative_discharge():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged_hospitalization(factory, scenario)
        async with factory() as session:
            await HospitalizationService(session).physical_departure(
                hospitalization_id, PhysicalDepartureCreate()
            )
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AccountService(session, STAFF).add_charge_item(
                    hospitalization_id, charge_payload()
                )
            return excinfo.value.status_code

    assert run_db(case) == 403


def test_only_the_administrator_role_bypasses_the_lock():
    assert RequestUser(role="ADMIN", name="Ana").is_admin
    assert RequestUser(role="admin").is_admin
    assert not RequestUser(role="DOCTOR").is_admin
    assert not RequestUser(role="NURSE").is_admin
    assert not STAFF.is_admin
