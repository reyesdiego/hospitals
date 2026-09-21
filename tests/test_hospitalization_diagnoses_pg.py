"""Diagnósticos de una internación: los de ingreso y los de egreso."""

import pytest

from app.core.exceptions import DomainError
from app.core.users import RequestUser
from app.models.diagnosis import DiagnosisCode, DiagnosisLevel, DiagnosisRole, DiagnosisStage
from app.schemas.diagnosis import (
    HospitalizationDiagnosisCreate,
    HospitalizationDiagnosisUpdate,
)
from app.schemas.workflow import ClinicalDischargeCreate
from app.services.diagnosis import HospitalizationDiagnosisService
from app.services.hospitalization import HospitalizationService
from tests.conftest import requires_postgres, run_db
from tests.factories import admission_payload, build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

NURSE = RequestUser(role="NURSE", name="Enf. Perez")
ADMIN = RequestUser(role="ADMIN", name="Ana Supervisora")

CODES = [
    ("J00-J99", "Enfermedades del sistema respiratorio", DiagnosisLevel.CHAPTER, None),
    ("J15", "Neumonía bacteriana", DiagnosisLevel.CATEGORY, "J00-J99"),
    ("J159", "Neumonía bacteriana, no especificada", DiagnosisLevel.SUBCATEGORY, "J15"),
    ("E11", "Diabetes mellitus tipo 2", DiagnosisLevel.CATEGORY, "J00-J99"),
    ("I10", "Hipertensión esencial", DiagnosisLevel.CATEGORY, "J00-J99"),
]


async def load_codes(session) -> None:
    for code, description, level, parent in CODES:
        session.add(
            DiagnosisCode(
                code=code,
                description=description,
                level=level,
                parent_code=parent,
                chapter_code="J00-J99",
            )
        )
        await session.flush()
    await session.commit()


def test_the_admission_records_the_presumptive_diagnoses():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        async with factory() as session:
            admission = await __import__(
                "app.services.admission", fromlist=["AdmissionWorkflowService"]
            ).AdmissionWorkflowService(session).create(
                admission_payload(
                    scenario,
                    diagnoses=[
                        {"code": "J159", "role": "PRINCIPAL"},
                        {"code": "E11", "role": "COMORBIDITY"},
                    ],
                )
            )
            hospitalization_id = admission.hospitalization_id
        async with factory() as check:
            entries = await HospitalizationDiagnosisService(check).list_for_hospitalization(
                hospitalization_id
            )
            return [(entry.code, entry.role, entry.stage, entry.description) for entry in entries]

    entries = run_db(case)

    # El principal primero: es el que contesta por qué está internado.
    assert entries[0][:3] == ("J159", DiagnosisRole.PRINCIPAL, DiagnosisStage.ADMISSION)
    assert entries[1][:3] == ("E11", DiagnosisRole.COMORBIDITY, DiagnosisStage.ADMISSION)
    # El texto queda congelado del catálogo.
    assert entries[0][3] == "Neumonía bacteriana, no especificada"


def test_only_a_codifiable_and_active_code_can_be_recorded():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            service = HospitalizationDiagnosisService(session)
            with pytest.raises(DomainError) as chapter:
                await service.add(
                    hospitalization_id,
                    HospitalizationDiagnosisCreate(code="J00-J99"),
                )
            with pytest.raises(DomainError) as unknown:
                await service.add(
                    hospitalization_id,
                    HospitalizationDiagnosisCreate(code="Z999"),
                )
            return chapter.value.status_code, unknown.value.status_code

    assert run_db(case) == (422, 404)


def test_there_is_only_one_principal_diagnosis_per_stage():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            service = HospitalizationDiagnosisService(session)
            await service.add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(code="J159", role=DiagnosisRole.PRINCIPAL),
            )
            with pytest.raises(DomainError) as error:
                await service.add(
                    hospitalization_id,
                    HospitalizationDiagnosisCreate(code="I10", role=DiagnosisRole.PRINCIPAL),
                )
            # El mismo código en el egreso sí: es otro momento de la internación.
            await service.add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(
                    code="J159",
                    role=DiagnosisRole.PRINCIPAL,
                    stage=DiagnosisStage.DISCHARGE,
                ),
            )
            entries = await service.list_for_hospitalization(hospitalization_id)
            return error.value.status_code, len(entries)

    status_code, total = run_db(case)

    assert status_code == 409
    assert total == 2


def test_the_clinical_discharge_records_the_final_diagnoses():
    """Lo que se sospechó al ingreso y lo que resultó conviven en la historia."""

    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await __import__(
                "app.services.bed_assignment", fromlist=["BedAssignmentService"]
            ).BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
        async with factory() as session:
            await HospitalizationDiagnosisService(session).add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(code="J159", role=DiagnosisRole.PRINCIPAL),
            )
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(
                    diagnoses=[
                        HospitalizationDiagnosisCreate(
                            code="J15",
                            role=DiagnosisRole.PRINCIPAL,
                        ),
                        HospitalizationDiagnosisCreate(code="I10"),
                    ],
                ),
            )
        async with factory() as check:
            service = HospitalizationDiagnosisService(check)
            admission_stage = await service.list_for_hospitalization(
                hospitalization_id, stage=DiagnosisStage.ADMISSION
            )
            discharge_stage = await service.list_for_hospitalization(
                hospitalization_id, stage=DiagnosisStage.DISCHARGE
            )
            return (
                [entry.code for entry in admission_stage],
                [(entry.code, entry.role) for entry in discharge_stage],
            )

    admission_codes, discharge_codes = run_db(case)

    assert admission_codes == ["J159"]
    assert discharge_codes == [("J15", DiagnosisRole.PRINCIPAL), ("I10", DiagnosisRole.SECONDARY)]


def test_after_the_medical_discharge_only_an_admin_touches_the_diagnoses():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await __import__(
                "app.services.bed_assignment", fromlist=["BedAssignmentService"]
            ).BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationDiagnosisService(session, NURSE).add(
                    hospitalization_id,
                    HospitalizationDiagnosisCreate(code="J159"),
                )
            status_code = error.value.status_code
        async with factory() as session:
            entry = await HospitalizationDiagnosisService(session, ADMIN).add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(code="J159", stage=DiagnosisStage.DISCHARGE),
            )
            return status_code, entry.code

    status_code, code = run_db(case)

    assert status_code == 403
    assert code == "J159"


def test_a_diagnosis_can_be_re_roled_and_removed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            service = HospitalizationDiagnosisService(session)
            first = await service.add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(code="J159", role=DiagnosisRole.PRINCIPAL),
            )
            second = await service.add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(code="I10"),
            )
            first_id, second_id = first.id, second.id
        async with factory() as session:
            service = HospitalizationDiagnosisService(session)
            # Para mover el principal, primero se libera el que lo tenía.
            await service.update(
                hospitalization_id,
                first_id,
                HospitalizationDiagnosisUpdate(role=DiagnosisRole.SECONDARY),
            )
            await service.update(
                hospitalization_id,
                second_id,
                HospitalizationDiagnosisUpdate(role=DiagnosisRole.PRINCIPAL),
            )
            await service.remove(hospitalization_id, first_id)
            entries = await service.list_for_hospitalization(hospitalization_id)
            return [(entry.code, entry.role) for entry in entries]

    assert run_db(case) == [("I10", DiagnosisRole.PRINCIPAL)]
