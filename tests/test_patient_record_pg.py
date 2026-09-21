"""Historia clínica del paciente: todo lo suyo, visto por paciente y no por internación."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.models.diagnosis import DiagnosisCode, DiagnosisLevel, DiagnosisRole
from app.models.practice import (
    MedicalPractice,
    Nomenclador,
    PracticeChapter,
    PracticeType,
)
from app.models.prescription import PrescriptionKind
from app.schemas.diagnosis import HospitalizationDiagnosisCreate
from app.schemas.practice import HospitalizationPracticeCreate, MedicalPracticeTariffCreate
from app.schemas.prescription import DischargePrescriptionCreate
from app.schemas.workflow import ChargeItemCreate, ClinicalDischargeCreate, PaymentCreate
from app.services.account import AccountService
from app.services.bed_assignment import BedAssignmentService
from app.services.diagnosis import HospitalizationDiagnosisService
from app.services.patient_record import (
    build_record,
    consultations,
    performed_practices,
)
from app.services.practice import HospitalizationPracticeService, MedicalPracticeService
from app.services.prescription import DischargePrescriptionService
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres


async def load_catalog(session):
    """Una consulta y una práctica, más el diagnóstico con el que se va a codificar."""

    consulta = MedicalPractice(
        nomenclador=Nomenclador.NACIONAL,
        code="42.01.01",
        name="Consulta en consultorio",
        chapter=PracticeChapter.CONSULTAS,
        practice_type=PracticeType.CONSULTA,
    )
    radiografia = MedicalPractice(
        nomenclador=Nomenclador.NACIONAL,
        code="34.01.01",
        name="Radiografia de torax",
        chapter=PracticeChapter.DIAGNOSTICO_POR_IMAGENES,
        practice_type=PracticeType.IMAGENES,
    )
    session.add_all([consulta, radiografia])
    session.add(
        DiagnosisCode(
            code="J15",
            description="Neumonía bacteriana",
            level=DiagnosisLevel.CATEGORY,
            chapter_code="J00-J99",
        )
    )
    await session.commit()
    service = MedicalPracticeService(session)
    for practice in (consulta, radiografia):
        await service.create_tariff(
            practice.id,
            MedicalPracticeTariffCreate(total_amount=Decimal("5000.00"), valid_from=date(2020, 1, 1)),
        )
    return consulta, radiografia


async def full_stay(factory):
    """Una internación completa: consulta, práctica, diagnóstico, receta, cargo y pago."""

    async with factory() as setup:
        scenario = await build_scenario(setup)
        consulta, radiografia = await load_catalog(setup)
    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    async with factory() as session:
        service = HospitalizationPracticeService(session)
        for practice_id in (consulta.id, radiografia.id):
            await service.register(
                hospitalization_id,
                HospitalizationPracticeCreate(
                    practice_id=practice_id,
                    prescribed_by_id=scenario.practitioner_id,
                    performed_at="2026-09-20T10:00:00Z",
                ),
            )
    async with factory() as session:
        await HospitalizationDiagnosisService(session).add(
            hospitalization_id,
            HospitalizationDiagnosisCreate(code="J15", role=DiagnosisRole.PRINCIPAL),
        )
    async with factory() as session:
        await DischargePrescriptionService(session).add(
            hospitalization_id,
            DischargePrescriptionCreate(
                kind=PrescriptionKind.MEDICATION,
                description="Amoxicilina 500 mg",
                dosage="1 cada 8 horas",
                prescribed_by_id=scenario.practitioner_id,
            ),
        )
    async with factory() as session:
        await AccountService(session).register_payment(
            hospitalization_id,
            PaymentCreate(amount="4000.00"),
        )
    return scenario, hospitalization_id


def test_the_record_gathers_everything_the_patient_has():
    async def case(factory):
        scenario, hospitalization_id = await full_stay(factory)
        async with factory() as check:
            record = await build_record(check, scenario.patient_id)
            return (
                record,
                performed_practices(record),
                consultations(record),
                hospitalization_id,
            )

    record, performed, consults, hospitalization_id = run_db(case)

    assert record.patient.last_name == "Gomez"
    assert [stay.id for stay in record.hospitalizations] == [hospitalization_id]
    assert record.locations[hospitalization_id].facility_name == "Hospital Central"
    assert record.locations[hospitalization_id].service_name == "Clínica Médica"
    assert record.locations[hospitalization_id].bed_label.startswith("101-0")
    assert record.principal_diagnosis(hospitalization_id) == "J15 - Neumonía bacteriana"
    # Dos prácticas realizadas, una de ellas consulta.
    assert performed == 2
    assert consults == 1
    assert [item.description for item in record.prescriptions] == ["Amoxicilina 500 mg"]
    # Paciente particular: las dos prácticas son suyas, pagó 4000 de 10000.
    assert record.patient_charged == Decimal("10000.00")
    assert record.paid == Decimal("4000.00")
    assert record.balance == Decimal("6000.00")


def test_an_open_stay_is_counted_as_open():
    async def case(factory):
        scenario, hospitalization_id = await full_stay(factory)
        async with factory() as check:
            record = await build_record(check, scenario.patient_id)
            open_before = record.open_stays
        async with factory() as session:
            await AccountService(session).add_charge_item(
                hospitalization_id,
                ChargeItemCreate(
                    category="HOSPITALIZATION_DAY",
                    description="Dia de internacion",
                    quantity=1,
                    unit_price="0.00",
                ),
            )
        async with factory() as session:
            await __import__(
                "app.services.hospitalization", fromlist=["HospitalizationService"]
            ).HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as check:
            record = await build_record(check, scenario.patient_id)
            return open_before, record.open_stays, record.hospitalizations[0].status.value

    open_before, open_after, status = run_db(case)

    assert open_before == 1
    assert open_after == 0
    assert status == "CLINICALLY_DISCHARGED"


def test_a_patient_without_hospitalizations_has_an_empty_record():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as check:
            record = await build_record(check, scenario.other_patient_id)
            return record

    record = run_db(case)

    assert record.hospitalizations == []
    assert record.diagnoses == []
    assert record.practices == []
    assert record.payments == []
    assert record.patient_charged == Decimal(0)
    assert record.balance == Decimal(0)


def test_an_unknown_patient_is_rejected():
    async def case(factory):
        async with factory() as check:
            with pytest.raises(DomainError) as error:
                await build_record(check, uuid.uuid4())
            return error.value.status_code

    assert run_db(case) == 404


def test_the_practices_say_which_ones_are_consultations():
    async def case(factory):
        scenario, _ = await full_stay(factory)
        async with factory() as check:
            record = await build_record(check, scenario.patient_id)
            return sorted(
                (order.practice_code, is_consultation, str(amount))
                for order, is_consultation, amount in record.practices
            )

    rows = run_db(case)

    assert rows == [
        ("34.01.01", False, "5000.00"),
        ("42.01.01", True, "5000.00"),
    ]
