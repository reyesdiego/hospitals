"""Recetas e indicaciones que el paciente se lleva al alta, y su impresión."""

import base64
import re
import uuid
import zlib
from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.core.users import RequestUser
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.practice import Nomenclador, PracticeChapter, PracticeType
from app.models.prescription import PrescriptionKind
from app.schemas.practice import MedicalPracticeCreate
from app.schemas.prescription import (
    DischargePrescriptionCreate,
    DischargePrescriptionUpdate,
)
from app.schemas.workflow import ClinicalDischargeCreate
from app.services.bed_assignment import BedAssignmentService
from app.services.hospitalization import HospitalizationService
from app.services.practice import MedicalPracticeService
from app.services.prescription import DischargePrescriptionService, build_document
from app.services.prescription_pdf import render
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

DOCTOR = RequestUser(role="DOCTOR", name="Dra. Lopez")


def printed_lines(pdf: bytes) -> list[str]:
    """Texto que quedó impreso, sacado de los streams del PDF."""

    lines: list[str] = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        try:
            data = zlib.decompress(base64.a85decode(stream.strip(b"\r\n"), adobe=True))
        except (ValueError, zlib.error):  # un stream que no es texto no aporta
            continue
        lines.extend(re.findall(r"\((.*?)\) Tj", data.decode("latin-1")))
    return lines


async def discharged(factory, scenario) -> uuid.UUID:
    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(
            session,
            scenario,
            coverage={"payer_name": "OMINT", "plan_name": "4500", "member_number": "12345678"},
        )
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    async with factory() as session:
        await HospitalizationService(session).clinical_discharge(
            hospitalization_id,
            ClinicalDischargeCreate(
                discharge_reason="Evolución favorable",
                ordered_by_practitioner_id=scenario.practitioner_id,
            ),
        )
    return hospitalization_id


def medication(**overrides) -> DischargePrescriptionCreate:
    data: dict = {
        "kind": PrescriptionKind.MEDICATION,
        "description": "Amoxicilina",
        "presentation": "comprimidos 500 mg",
        "dosage": "1 cada 8 horas",
        "quantity": Decimal(2),
        "duration_days": 7,
        "instructions": "Tomar con las comidas",
    }
    data.update(overrides)
    return DischargePrescriptionCreate(**data)


def test_the_doctor_writes_the_prescriptions_when_signing_the_discharge():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged(factory, scenario)
        async with factory() as session:
            practice = await MedicalPracticeService(session).create(
                MedicalPracticeCreate(
                    nomenclador=Nomenclador.NBU,
                    code="66.01.01",
                    name="Hemograma completo",
                    chapter=PracticeChapter.LABORATORIO,
                    practice_type=PracticeType.LABORATORIO,
                )
            )
            practice_id = practice.id
        async with factory() as session:
            service = DischargePrescriptionService(session, DOCTOR)
            drug = await service.add(
                hospitalization_id,
                medication(prescribed_by_id=scenario.practitioner_id),
            )
            drug_signer = drug.prescribed_by_user_name
        async with factory() as session:
            study = await DischargePrescriptionService(session, DOCTOR).add(
                hospitalization_id,
                DischargePrescriptionCreate(
                    kind=PrescriptionKind.PRACTICE,
                    practice_id=practice_id,
                    instructions="Control a los 10 dias",
                ),
            )
            # El nombre de la práctica se copia del nomenclador.
            study_description = study.description
        async with factory() as session:
            items = await DischargePrescriptionService(session).list_for_hospitalization(
                hospitalization_id
            )
            return drug_signer, study_description, [(i.kind, i.description) for i in items]

    signer, study, items = run_db(case)
    assert signer == "Dra. Lopez"
    assert study == "66.01.01 - Hemograma completo"
    assert items == [
        (PrescriptionKind.MEDICATION, "Amoxicilina"),
        (PrescriptionKind.PRACTICE, "66.01.01 - Hemograma completo"),
    ]


def test_they_can_be_corrected_and_removed_while_the_patient_is_leaving():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged(factory, scenario)
        async with factory() as session:
            item = await DischargePrescriptionService(session, DOCTOR).add(
                hospitalization_id, medication()
            )
            item_id = item.id
        async with factory() as session:
            fixed = await DischargePrescriptionService(session, DOCTOR).update(
                hospitalization_id,
                item_id,
                DischargePrescriptionUpdate(
                    kind=PrescriptionKind.MEDICATION,
                    description="Amoxicilina",
                    presentation="comprimidos 875 mg",
                    dosage="1 cada 12 horas",
                    quantity=Decimal(1),
                    duration_days=10,
                ),
            )
            dosage = fixed.dosage
        async with factory() as session:
            await DischargePrescriptionService(session, DOCTOR).remove(
                hospitalization_id, item_id
            )
        async with factory() as session:
            left = await DischargePrescriptionService(session).list_for_hospitalization(
                hospitalization_id
            )
            return dosage, left

    dosage, left = run_db(case)
    assert dosage == "1 cada 12 horas"
    assert left == []


def test_a_closed_hospitalization_no_longer_accepts_indications():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged(factory, scenario)
        async with factory() as session:
            hospitalization = await session.get(Hospitalization, hospitalization_id)
            hospitalization.status = HospitalizationStatus.CLOSED
            await session.commit()
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await DischargePrescriptionService(session, DOCTOR).add(
                    hospitalization_id, medication()
                )
            return excinfo.value.status_code, excinfo.value.message

    status_code, message = run_db(case)
    assert status_code == 409
    assert "ya está cerrada" in message


def test_medication_is_free_text_and_cannot_come_from_the_nomenclador():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged(factory, scenario)
        async with factory() as session:
            practice = await MedicalPracticeService(session).create(
                MedicalPracticeCreate(
                    nomenclador=Nomenclador.NACIONAL,
                    code="42.01.01",
                    name="Consulta",
                    chapter=PracticeChapter.CONSULTAS,
                    practice_type=PracticeType.CONSULTA,
                )
            )
            practice_id = practice.id
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await DischargePrescriptionService(session, DOCTOR).add(
                    hospitalization_id,
                    DischargePrescriptionCreate(
                        kind=PrescriptionKind.MEDICATION,
                        description="Amoxicilina",
                        practice_id=practice_id,
                    ),
                )
            first = excinfo.value.status_code
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await DischargePrescriptionService(session, DOCTOR).add(
                    hospitalization_id,
                    DischargePrescriptionCreate(kind=PrescriptionKind.MEDICATION),
                )
            return first, excinfo.value.status_code, excinfo.value.message

    first, second, message = run_db(case)
    assert first == 422
    assert second == 422
    assert "Informe qué se le indica" in message


def test_the_pdf_has_the_prescription_the_practices_and_who_signs():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged(factory, scenario)
        async with factory() as session:
            await DischargePrescriptionService(session, DOCTOR).add(
                hospitalization_id, medication(prescribed_by_id=scenario.practitioner_id)
            )
        async with factory() as session:
            await DischargePrescriptionService(session, DOCTOR).add(
                hospitalization_id,
                DischargePrescriptionCreate(
                    kind=PrescriptionKind.PRACTICE,
                    description="Ecografia abdominal",
                    instructions="En ayunas",
                ),
            )
        async with factory() as session:
            document = await build_document(session, hospitalization_id)
            return render(document), document.patient_name

    pdf, patient_name = run_db(case)
    assert pdf.startswith(b"%PDF")
    lines = printed_lines(pdf)
    assert "RECETA MEDICA" in lines
    assert "INDICACION DE PRACTICAS" in lines
    assert any(line.startswith("1. Amoxicilina - comprimidos 500 mg") for line in lines)
    assert "Posologia: 1 cada 8 horas" in lines
    assert "1. Ecografia abdominal" in lines
    assert "En ayunas" in lines
    assert "Firma y sello" in lines
    # El paciente y su cobertura salen impresos en las dos hojas.
    assert lines.count(patient_name.replace("ó", "\\363")) == 2 or lines.count(patient_name) == 2
    assert lines.count("OMINT - afiliado 12345678") == 2


def test_the_pdf_says_so_when_there_is_nothing_indicated():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await discharged(factory, scenario)
        async with factory() as session:
            document = await build_document(session, hospitalization_id)
            return render(document)

    lines = printed_lines(run_db(case))
    assert "Sin medicacion indicada al alta." in lines
    assert "Sin practicas indicadas al alta." in lines


def test_an_unknown_hospitalization_has_no_document():
    async def case(factory):
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await build_document(session, uuid.uuid4())
            return excinfo.value.status_code

    assert run_db(case) == 404
