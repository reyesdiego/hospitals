"""Registro de administración: lo que enfermería efectivamente le dio al paciente."""

from datetime import UTC, datetime, time, timedelta

import pytest

from app.core.exceptions import DomainError
from app.core.users import RequestUser
from app.db.maintenance.treatment_schedules import migrate_schedules
from app.models.treatment import (
    AdministrationStatus,
    MedicationRoute,
    ScheduleKind,
    TreatmentStatus,
)
from app.schemas.treatment import (
    AdministrationCreate,
    AdministrationVoidCreate,
    TreatmentCreate,
    TreatmentStopCreate,
)
from app.services.bed_assignment import BedAssignmentService
from app.services.treatment import (
    HospitalizationTreatmentService,
    TreatmentAdministrationService,
)
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

DOCTOR = RequestUser(role="DOCTOR", name="Dra. Lopez")
NURSE = RequestUser(role="NURSE", name="Enf. Perez")


async def stay_with_medication(factory):
    """Una internación en cama con amoxicilina indicada hace dos horas, cada 8 horas."""

    async with factory() as setup:
        scenario = await build_scenario(setup)
    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    async with factory() as session:
        treatment = await HospitalizationTreatmentService(session, DOCTOR).add(
            hospitalization_id,
            TreatmentCreate(
                description="Amoxicilina",
                presentation="500 mg",
                dose="1 comprimido",
                route=MedicationRoute.ORAL,
                frequency="cada 8 horas",
                started_at=datetime.now(UTC) - timedelta(hours=2),
                prescribed_by_id=scenario.practitioner_id,
            ),
        )
        treatment_id = treatment.id
    return scenario, hospitalization_id, treatment_id


def test_a_dose_takes_the_indicated_dose_and_route_by_default():
    async def case(factory):
        scenario, hospitalization_id, treatment_id = await stay_with_medication(factory)
        async with factory() as session:
            entry = await TreatmentAdministrationService(session, NURSE).register(
                hospitalization_id,
                treatment_id,
                AdministrationCreate(administered_by_id=scenario.practitioner_id),
            )
            return entry.status, entry.dose, entry.route, entry.recorded_by_user_name

    status, dose, route, recorded_by = run_db(case)

    assert status == AdministrationStatus.GIVEN
    # Lo habitual es dar lo indicado: la dosis y la via salen de la indicacion.
    assert dose == "1 comprimido"
    assert route == MedicationRoute.ORAL
    assert recorded_by == "Enf. Perez"


def test_an_omitted_dose_needs_its_reason_and_stays_in_the_record():
    async def case(factory):
        _, hospitalization_id, treatment_id = await stay_with_medication(factory)
        async with factory() as session:
            service = TreatmentAdministrationService(session, NURSE)
            with pytest.raises(DomainError) as error:
                await service.register(
                    hospitalization_id,
                    treatment_id,
                    AdministrationCreate(status=AdministrationStatus.OMITTED),
                )
            status_code = error.value.status_code
        async with factory() as session:
            await TreatmentAdministrationService(session, NURSE).register(
                hospitalization_id,
                treatment_id,
                AdministrationCreate(
                    status=AdministrationStatus.OMITTED,
                    omission_reason="Paciente en ayunas para cirugia",
                ),
            )
        async with factory() as check:
            entries = await TreatmentAdministrationService(check).list_for_treatment(
                hospitalization_id, treatment_id
            )
            return status_code, entries[0].status, entries[0].omission_reason

    status_code, status, reason = run_db(case)

    assert status_code == 422
    assert status == AdministrationStatus.OMITTED
    assert reason == "Paciente en ayunas para cirugia"


def test_a_dose_cannot_be_before_the_indication_started():
    async def case(factory):
        _, hospitalization_id, treatment_id = await stay_with_medication(factory)
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await TreatmentAdministrationService(session, NURSE).register(
                    hospitalization_id,
                    treatment_id,
                    AdministrationCreate(
                        administered_at=datetime.now(UTC) - timedelta(days=1),
                    ),
                )
            return error.value.status_code

    assert run_db(case) == 422


def test_a_suspended_indication_takes_the_dose_that_was_left_unrecorded_but_no_new_ones():
    async def case(factory):
        _, hospitalization_id, treatment_id = await stay_with_medication(factory)
        stopped_at = datetime.now(UTC)
        async with factory() as session:
            await HospitalizationTreatmentService(session, DOCTOR).stop(
                hospitalization_id,
                treatment_id,
                TreatmentStopCreate(
                    status=TreatmentStatus.SUSPENDED,
                    ended_at=stopped_at,
                    reason="Cambio de esquema",
                ),
            )
        async with factory() as session:
            # La toma que quedó sin cargar, anterior a la suspensión: entra.
            late = await TreatmentAdministrationService(session, NURSE).register(
                hospitalization_id,
                treatment_id,
                AdministrationCreate(administered_at=stopped_at - timedelta(minutes=30)),
            )
            late_status = late.status
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await TreatmentAdministrationService(session, NURSE).register(
                    hospitalization_id,
                    treatment_id,
                    AdministrationCreate(administered_at=stopped_at + timedelta(hours=1)),
                )
            return late_status, error.value.status_code

    late_status, status_code = run_db(case)

    assert late_status == AdministrationStatus.GIVEN
    assert status_code == 409


def test_a_dose_loaded_by_mistake_is_voided_and_stops_counting():
    async def case(factory):
        _, hospitalization_id, treatment_id = await stay_with_medication(factory)
        async with factory() as session:
            entry = await TreatmentAdministrationService(session, NURSE).register(
                hospitalization_id,
                treatment_id,
                AdministrationCreate(),
            )
            entry_id = entry.id
        async with factory() as session:
            await TreatmentAdministrationService(session, NURSE).void(
                hospitalization_id,
                treatment_id,
                entry_id,
                AdministrationVoidCreate(reason="Cargada en el paciente equivocado"),
            )
        async with factory() as check:
            service = TreatmentAdministrationService(check)
            entries = await service.list_for_treatment(hospitalization_id, treatment_id)
            rounds = await service.medication_round(hospitalization_id=hospitalization_id)
            return entries[0].status, rounds[0].administrations, rounds[0].last_administered_at

    status, administrations, last = run_db(case)

    assert status == AdministrationStatus.VOID
    # Una toma anulada no cuenta como dada: la indicación vuelve a figurar sin tomas.
    assert administrations == 0
    assert last is None


def test_the_medication_round_shows_what_has_been_waiting_longest():
    async def case(factory):
        _, hospitalization_id, treatment_id = await stay_with_medication(factory)
        async with factory() as session:
            await HospitalizationTreatmentService(session, DOCTOR).add(
                hospitalization_id,
                TreatmentCreate(description="Omeprazol", dose="20 mg"),
            )
        async with factory() as session:
            await TreatmentAdministrationService(session, NURSE).register(
                hospitalization_id,
                treatment_id,
                AdministrationCreate(),
            )
        async with factory() as check:
            rounds = await TreatmentAdministrationService(check).medication_round()
            return [
                (item.treatment.description, item.administrations, item.bed_code)
                for item in rounds
            ]

    rounds = run_db(case)

    # Primero lo que nunca se dio; la amoxicilina ya tiene su toma.
    assert [item[0] for item in rounds] == ["Omeprazol", "Amoxicilina"]
    assert rounds[0][1] == 0
    assert rounds[1][1] == 1
    assert rounds[0][2].startswith("101-0")


def test_the_round_marks_the_overdue_ones_first():
    """Con esquema estructurado la vuelta sabe qué se pasó de hora."""

    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
        async with factory() as session:
            service = HospitalizationTreatmentService(session, DOCTOR)
            # Cada 6 horas desde hace 8: la primera toma ya se paso de hora.
            await service.add(
                hospitalization_id,
                TreatmentCreate(
                    description="Amoxicilina",
                    dose="500 mg",
                    schedule_kind=ScheduleKind.INTERVAL,
                    interval_hours=6,
                    started_at=datetime.now(UTC) - timedelta(hours=8),
                ),
            )
            # A demanda: no tiene horario que vencerse.
            await service.add(
                hospitalization_id,
                TreatmentCreate(
                    description="Dipirona",
                    dose="1 g",
                    schedule_kind=ScheduleKind.AS_NEEDED,
                    started_at=datetime.now(UTC) - timedelta(hours=8),
                ),
            )
        async with factory() as check:
            service = TreatmentAdministrationService(check)
            rounds = await service.medication_round()
            overdue = await service.medication_round(overdue_only=True)
            return (
                [(item.treatment.description, item.overdue) for item in rounds],
                [item.treatment.description for item in overdue],
                rounds[0].treatment.frequency,
                [slot.state.value for slot in rounds[0].slots][:1],
            )

    rounds, overdue, frequency, first_state = run_db(case)

    # La vencida encabeza la vuelta.
    assert rounds[0] == ("Amoxicilina", True)
    assert ("Dipirona", False) in rounds
    assert overdue == ["Amoxicilina"]
    # La frecuencia se escribe sola desde el esquema.
    assert frequency == "cada 6 horas"
    assert first_state == ["OVERDUE"]


def test_fixed_times_give_the_schedule_of_the_day():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
        async with factory() as session:
            await HospitalizationTreatmentService(session, DOCTOR).add(
                hospitalization_id,
                TreatmentCreate(
                    description="Enalapril",
                    dose="10 mg",
                    schedule_kind=ScheduleKind.TIMES,
                    times_of_day=[time(8, 0), time(20, 0)],
                    started_at=datetime.now(UTC) - timedelta(days=1),
                ),
            )
        async with factory() as check:
            rounds = await TreatmentAdministrationService(check).medication_round()
            return rounds[0].treatment.frequency, len(rounds[0].slots) > 0

    frequency, has_slots = run_db(case)

    assert frequency == "08:00 - 20:00"
    assert has_slots


def test_the_existing_indications_are_migrated_to_the_structured_schedule():
    """Las cargadas antes del esquema: se lee su frecuencia y se completa."""

    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            service = HospitalizationTreatmentService(session, DOCTOR)
            for description, frequency in (
                ("Amoxicilina", "cada 8 horas"),
                ("Enalapril", "08:00 y 20:00"),
                ("Dipirona", "segun necesidad del paciente"),
            ):
                await service.add(
                    hospitalization_id,
                    TreatmentCreate(description=description, frequency=frequency),
                )
        async with factory() as session:
            preview = await migrate_schedules(session)
        async with factory() as session:
            await migrate_schedules(session, apply=True)
        async with factory() as check:
            entries = await HospitalizationTreatmentService(check).list_for_hospitalization(
                hospitalization_id
            )
            by_name = {entry.description: entry for entry in entries}
            return (
                len(preview.understood),
                len(preview.unknown),
                by_name["Amoxicilina"].schedule_kind,
                by_name["Amoxicilina"].interval_hours,
                by_name["Enalapril"].schedule_kind,
                by_name["Enalapril"].times_of_day,
                by_name["Dipirona"].schedule_kind,
                by_name["Amoxicilina"].frequency,
            )

    (
        understood,
        unknown,
        amoxi_kind,
        amoxi_hours,
        enalapril_kind,
        enalapril_times,
        dipirona_kind,
        amoxi_frequency,
    ) = run_db(case)

    assert (understood, unknown) == (2, 1)
    assert amoxi_kind == ScheduleKind.INTERVAL
    assert amoxi_hours == 8
    assert enalapril_kind == ScheduleKind.TIMES
    assert enalapril_times == [time(8, 0), time(20, 0)]
    # Lo que no se entiende queda como estaba.
    assert dipirona_kind == ScheduleKind.AS_NEEDED
    # El texto original se respeta: es lo que escribió quien indicó.
    assert amoxi_frequency == "cada 8 horas"


def test_migrating_does_not_touch_what_someone_already_configured():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await HospitalizationTreatmentService(session, DOCTOR).add(
                hospitalization_id,
                TreatmentCreate(
                    description="Enalapril",
                    # Alguien ya lo configuró a mano, y el texto dice otra cosa.
                    frequency="cada 8 horas",
                    schedule_kind=ScheduleKind.TIMES,
                    times_of_day=[time(9, 0)],
                ),
            )
        async with factory() as session:
            report = await migrate_schedules(session, apply=True)
        async with factory() as check:
            entry = (
                await HospitalizationTreatmentService(check).list_for_hospitalization(
                    hospitalization_id
                )
            )[0]
            return len(report.rows), entry.schedule_kind, entry.times_of_day

    rows, kind, times = run_db(case)

    assert rows == 0
    assert kind == ScheduleKind.TIMES
    assert times == [time(9, 0)]
