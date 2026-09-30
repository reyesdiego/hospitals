"""El resumen de alta se arma con lo que ya está cargado en la internación."""

from datetime import UTC, datetime, timedelta

from app.models.diagnosis import DiagnosisCode, DiagnosisLevel, DiagnosisRole, DiagnosisStage
from app.models.prescription import PrescriptionKind
from app.models.treatment import AdministrationStatus, MedicationRoute, ScheduleKind
from app.schemas.diagnosis import HospitalizationDiagnosisCreate
from app.schemas.prescription import DischargePrescriptionCreate
from app.schemas.treatment import (
    AdministrationCreate,
    ClinicalNoteCreate,
    ClinicalNoteVoidCreate,
    TreatmentCreate,
)
from app.schemas.workflow import ClinicalDischargeCreate
from app.services.bed_assignment import BedAssignmentService
from app.services.diagnosis import HospitalizationDiagnosisService
from app.services.discharge_summary import build_summary
from app.services.discharge_summary_pdf import render
from app.services.hospitalization import HospitalizationService
from app.services.prescription import DischargePrescriptionService
from app.services.treatment import (
    HospitalizationNoteService,
    HospitalizationTreatmentService,
    TreatmentAdministrationService,
)
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

CODES = [
    ("J15", "Neumonía bacteriana", DiagnosisLevel.CATEGORY),
    ("J159", "Neumonía bacteriana, no especificada", DiagnosisLevel.SUBCATEGORY),
    ("I10", "Hipertensión esencial", DiagnosisLevel.CATEGORY),
]


async def load_codes(session) -> None:
    for code, description, level in CODES:
        session.add(DiagnosisCode(code=code, description=description, level=level))
    await session.commit()


async def discharged_stay(factory, scenario):
    """Una internación con diagnósticos de ingreso y de egreso, y alta médica dada."""

    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    async with factory() as session:
        await HospitalizationDiagnosisService(session).add(
            hospitalization_id,
            HospitalizationDiagnosisCreate(
                diagnosed_by_id=scenario.practitioner_id,
                code="J159",
                role=DiagnosisRole.PRINCIPAL,
            ),
        )
    async with factory() as session:
        treatment = await HospitalizationTreatmentService(session).add(
            hospitalization_id,
            TreatmentCreate(
                description="Amoxicilina",
                presentation="500 mg",
                dose="1 comprimido",
                route=MedicationRoute.ORAL,
                schedule_kind=ScheduleKind.INTERVAL,
                interval_hours=8,
                started_at=datetime.now(UTC) - timedelta(hours=10),
            ),
        )
        treatment_id = treatment.id
    async with factory() as session:
        service = TreatmentAdministrationService(session)
        await service.register(
            hospitalization_id,
            treatment_id,
            AdministrationCreate(administered_at=datetime.now(UTC) - timedelta(hours=9)),
        )
        await service.register(
            hospitalization_id,
            treatment_id,
            AdministrationCreate(
                status=AdministrationStatus.OMITTED,
                omission_reason="Paciente en ayunas",
                administered_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        )
    async with factory() as session:
        service = HospitalizationNoteService(session)
        await service.add(
            hospitalization_id,
            ClinicalNoteCreate(note="Paciente afebril, buena evolucion."),
        )
        voided = await service.add(
            hospitalization_id,
            ClinicalNoteCreate(note="Nota del paciente equivocado."),
        )
        voided_id = voided.id
    async with factory() as session:
        await HospitalizationNoteService(session).void(
            hospitalization_id,
            voided_id,
            ClinicalNoteVoidCreate(reason="Paciente equivocado"),
        )
    async with factory() as session:
        await DischargePrescriptionService(session).add(
            hospitalization_id,
            DischargePrescriptionCreate(
                kind=PrescriptionKind.MEDICATION,
                description="Amoxicilina 500 mg",
                presentation="Comprimidos",
                dosage="1 cada 8 horas",
                prescribed_by_id=scenario.practitioner_id,
            ),
        )
    async with factory() as session:
        await HospitalizationService(session).clinical_discharge(
            hospitalization_id,
            ClinicalDischargeCreate(
                discharge_reason="Evolucion favorable",
                ordered_by_practitioner_id=scenario.practitioner_id,
                instructions="Control en 7 dias",
                diagnoses=[
                    HospitalizationDiagnosisCreate(
                        diagnosed_by_id=scenario.practitioner_id,
                        code="J15",
                        role=DiagnosisRole.PRINCIPAL,
                    ),
                    HospitalizationDiagnosisCreate(
                        diagnosed_by_id=scenario.practitioner_id,
                        code="I10",
                        role=DiagnosisRole.COMORBIDITY,
                    ),
                ],
            ),
        )
    return hospitalization_id


def test_the_summary_carries_both_sets_of_diagnoses():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        hospitalization_id = await discharged_stay(factory, scenario)
        async with factory() as check:
            return await build_summary(check, hospitalization_id)

    summary = run_db(case)

    assert not summary.draft
    assert [item.code for item in summary.admission_diagnoses] == ["J159"]
    # El principal de egreso encabeza la lista.
    assert [(item.code, item.role) for item in summary.discharge_diagnoses] == [
        ("J15", DiagnosisRole.PRINCIPAL),
        ("I10", DiagnosisRole.COMORBIDITY),
    ]
    assert summary.patient_name == "Gomez, Ana"
    assert summary.facility_name == "Hospital Central"
    assert summary.service_name == "Clínica Médica"
    assert summary.bed_label.startswith("101-0")
    assert summary.physician == "Diaz, Marta"
    assert summary.length_of_stay_days == 0
    assert [item.description for item in summary.prescriptions] == ["Amoxicilina 500 mg"]


def test_the_summary_is_a_printable_pdf():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        hospitalization_id = await discharged_stay(factory, scenario)
        async with factory() as check:
            summary = await build_summary(check, hospitalization_id)
            return render(summary)

    pdf = run_db(case)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_without_the_medical_discharge_the_summary_is_a_draft():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await HospitalizationDiagnosisService(session).add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(
                    diagnosed_by_id=scenario.practitioner_id,
                    code="J159",
                    role=DiagnosisRole.PRINCIPAL,
                    stage=DiagnosisStage.ADMISSION,
                ),
            )
        async with factory() as check:
            summary = await build_summary(check, hospitalization_id)
            return summary.draft, len(summary.discharge_diagnoses), render(summary)[:4]

    draft, discharge_diagnoses, magic = run_db(case)

    assert draft
    assert discharge_diagnoses == 0
    assert magic == b"%PDF"


def test_the_summary_says_what_the_patient_received_and_how_he_evolved():
    """Lo que se le dio durante la internación y lo que escribió el médico cada día."""

    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            await load_codes(setup)
        hospitalization_id = await discharged_stay(factory, scenario)
        async with factory() as check:
            return await build_summary(check, hospitalization_id)

    summary = run_db(case)

    line = summary.treatments[0]
    assert line.treatment.description == "Amoxicilina"
    assert line.treatment.frequency == "cada 8 horas"
    # Una toma dada y una que no se pudo dar.
    assert (line.given, line.omitted) == (1, 1)
    # La nota anulada no llega al resumen.
    assert [note.note for note in summary.notes] == ["Paciente afebril, buena evolucion."]
