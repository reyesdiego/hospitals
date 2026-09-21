"""Informe estadístico de morbilidad: egresos contados por diagnóstico."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.diagnosis import DiagnosisCode, DiagnosisLevel, DiagnosisRole, DiagnosisStage
from app.models.discharge import DischargeType
from app.models.hospitalization import Hospitalization
from app.schemas.diagnosis import HospitalizationDiagnosisCreate
from app.schemas.workflow import ClinicalDischargeCreate
from app.services.bed_assignment import BedAssignmentService
from app.services.diagnosis import HospitalizationDiagnosisService
from app.services.hospitalization import HospitalizationService
from app.services.reports import MorbidityGrouping, morbidity_report
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

CODES = [
    ("J00-J99", "Enfermedades del sistema respiratorio", DiagnosisLevel.CHAPTER, None),
    ("I00-I99", "Enfermedades del sistema circulatorio", DiagnosisLevel.CHAPTER, None),
    ("J15", "Neumonía bacteriana", DiagnosisLevel.CATEGORY, "J00-J99"),
    ("I10", "Hipertensión esencial", DiagnosisLevel.CATEGORY, "I00-I99"),
    ("E11", "Diabetes mellitus tipo 2", DiagnosisLevel.CATEGORY, "I00-I99"),
]


async def load_codes(session) -> None:
    for code, description, level, chapter in CODES:
        session.add(
            DiagnosisCode(
                code=code,
                description=description,
                level=level,
                chapter_code=chapter or code,
            )
        )
        await session.flush()
    await session.commit()


async def discharged_with(
    factory,
    scenario,
    *,
    bed_index: int,
    principal: str,
    secondary: str | None = None,
    discharge_type: DischargeType = DischargeType.MEDICAL,
    stay_days: int = 3,
):
    """Una internación egresada con su diagnóstico de egreso y una estadía conocida."""

    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[bed_index])
    async with factory() as session:
        # El ingreso se corre hacia atrás para que la estadía sea la que quiere la prueba.
        hospitalization = await session.get(Hospitalization, hospitalization_id)
        hospitalization.admitted_at = datetime.now(UTC) - timedelta(days=stay_days)
        await session.commit()
    async with factory() as session:
        diagnoses = [
            HospitalizationDiagnosisCreate(code=principal, role=DiagnosisRole.PRINCIPAL)
        ]
        if secondary:
            diagnoses.append(HospitalizationDiagnosisCreate(code=secondary))
        await HospitalizationService(session).clinical_discharge(
            hospitalization_id,
            ClinicalDischargeCreate(discharge_type=discharge_type, diagnoses=diagnoses),
        )
    return hospitalization_id


async def three_discharges(factory):
    """Dos neumonías (una fallecida) y una hipertensión, todas egresadas."""

    async with factory() as setup:
        scenario = await build_scenario(setup, beds=4)
        await load_codes(setup)
    await discharged_with(factory, scenario, bed_index=0, principal="J15", secondary="E11")
    await discharged_with(
        factory,
        scenario,
        bed_index=1,
        principal="J15",
        discharge_type=DischargeType.DECEASED,
        stay_days=5,
    )
    await discharged_with(factory, scenario, bed_index=2, principal="I10", stay_days=1)
    return scenario


def test_the_report_counts_discharges_by_principal_diagnosis():
    async def case(factory):
        await three_discharges(factory)
        async with factory() as check:
            return await morbidity_report(check)

    report = run_db(case)

    assert report.total_episodes == 3
    assert report.uncoded_episodes == 0
    # Ordenado por cantidad de egresos.
    first, second = report.rows
    assert (first.key, first.episodes, first.deaths) == ("J15", 2, 1)
    assert first.description == "Neumonía bacteriana"
    assert first.average_stay_days == 4.0
    assert first.mortality_rate == 50.0
    assert (second.key, second.episodes, second.deaths) == ("I10", 1, 0)
    assert second.average_stay_days == 1.0


def test_the_report_can_be_grouped_by_chapter():
    async def case(factory):
        await three_discharges(factory)
        async with factory() as check:
            return await morbidity_report(check, group_by=MorbidityGrouping.CHAPTER)

    report = run_db(case)

    assert [(row.key, row.description, row.episodes) for row in report.rows] == [
        ("J00-J99", "Enfermedades del sistema respiratorio", 2),
        ("I00-I99", "Enfermedades del sistema circulatorio", 1),
    ]


def test_without_a_role_every_diagnosis_of_the_discharge_is_counted():
    async def case(factory):
        await three_discharges(factory)
        async with factory() as check:
            return await morbidity_report(check, role=None)

    report = run_db(case)

    # La comorbilidad E11 suma su propia fila: la misma internación aparece dos veces.
    assert {row.key: row.episodes for row in report.rows} == {"J15": 2, "I10": 1, "E11": 1}
    assert report.total_episodes == 4


def test_a_discharge_without_a_coded_diagnosis_is_reported_apart():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup, beds=3)
            await load_codes(setup)
        await discharged_with(factory, scenario, bed_index=0, principal="J15")
        # Esta egresa sin que nadie codifique el diagnóstico.
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[1])
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as check:
            return await morbidity_report(check)

    report = run_db(case)

    assert report.total_episodes == 1
    assert report.uncoded_episodes == 1


def test_the_period_and_the_stage_narrow_the_report():
    async def case(factory):
        scenario = await three_discharges(factory)
        async with factory() as session:
            # Un diagnóstico de ingreso, que el informe de egreso no tiene que contar.
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await HospitalizationDiagnosisService(session).add(
                hospitalization_id,
                HospitalizationDiagnosisCreate(code="E11", role=DiagnosisRole.PRINCIPAL),
            )
        async with factory() as check:
            # El informe recorta por fecha local, no por UTC.
            today = datetime.now(ZoneInfo(settings.timezone)).date()
            current = await morbidity_report(check, from_date=today, to_date=today)
            old = await morbidity_report(
                check,
                from_date=today - timedelta(days=30),
                to_date=today - timedelta(days=20),
            )
            admission_stage = await morbidity_report(
                check, stage=DiagnosisStage.ADMISSION
            )
            return current.total_episodes, old.total_episodes, admission_stage.total_episodes

    current, old, admission_stage = run_db(case)

    assert current == 3
    assert old == 0
    # El de ingreso es de una internación que no egresó: no entra en el informe.
    assert admission_stage == 0
