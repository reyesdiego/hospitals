"""Medicación, tratamiento y notas de evolución de la internación."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import DomainError
from app.core.users import RequestUser
from app.models.treatment import (
    ClinicalNoteKind,
    ClinicalNoteStatus,
    MedicationRoute,
    TreatmentKind,
    TreatmentStatus,
)
from app.schemas.treatment import (
    ClinicalNoteCreate,
    ClinicalNoteVoidCreate,
    TreatmentCreate,
    TreatmentStopCreate,
    TreatmentUpdate,
)
from app.schemas.workflow import ClinicalDischargeCreate
from app.services.bed_assignment import BedAssignmentService
from app.services.hospitalization import HospitalizationService
from app.services.treatment import (
    HospitalizationNoteService,
    HospitalizationTreatmentService,
)
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres

DOCTOR = RequestUser(role="DOCTOR", name="Dra. Lopez")
NURSE = RequestUser(role="NURSE", name="Enf. Perez")
ADMIN = RequestUser(role="ADMIN", name="Ana Supervisora")


async def admitted(factory):
    async with factory() as setup:
        scenario = await build_scenario(setup)
    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    return scenario, hospitalization_id


def test_the_medication_being_given_is_listed_first():
    async def case(factory):
        scenario, hospitalization_id = await admitted(factory)
        async with factory() as session:
            service = HospitalizationTreatmentService(session, DOCTOR)
            await service.add(
                hospitalization_id,
                TreatmentCreate(
                    description="Amoxicilina",
                    presentation="500 mg",
                    dose="1 comprimido",
                    route=MedicationRoute.ORAL,
                    frequency="cada 8 horas",
                    prescribed_by_id=scenario.practitioner_id,
                ),
            )
            kinesio = await service.add(
                hospitalization_id,
                TreatmentCreate(
                    kind=TreatmentKind.TREATMENT,
                    description="Kinesiologia respiratoria",
                    frequency="dos veces por dia",
                ),
            )
            kinesio_id = kinesio.id
        async with factory() as session:
            await HospitalizationTreatmentService(session, DOCTOR).stop(
                hospitalization_id,
                kinesio_id,
                TreatmentStopCreate(
                    status=TreatmentStatus.COMPLETED,
                    reason="Cumplio el plan indicado",
                ),
            )
        async with factory() as check:
            service = HospitalizationTreatmentService(check)
            everything = await service.list_for_hospitalization(hospitalization_id)
            active = await service.list_for_hospitalization(
                hospitalization_id, only_active=True
            )
            return (
                [(item.description, item.status) for item in everything],
                [item.description for item in active],
                everything[0].recorded_by_user_name,
                everything[0].route,
            )

    rows, active, recorded_by, route = run_db(case)

    # Lo que se esta dando ahora, arriba; lo cerrado, despues.
    assert rows == [
        ("Amoxicilina", TreatmentStatus.ACTIVE),
        ("Kinesiologia respiratoria", TreatmentStatus.COMPLETED),
    ]
    assert active == ["Amoxicilina"]
    assert recorded_by == "Dra. Lopez"
    assert route == MedicationRoute.ORAL


def test_a_closed_indication_is_not_edited_and_does_not_close_twice():
    async def case(factory):
        _, hospitalization_id = await admitted(factory)
        async with factory() as session:
            entry = await HospitalizationTreatmentService(session, DOCTOR).add(
                hospitalization_id,
                TreatmentCreate(description="Dipirona", dose="1 g"),
            )
            entry_id = entry.id
        async with factory() as session:
            await HospitalizationTreatmentService(session, DOCTOR).stop(
                hospitalization_id,
                entry_id,
                TreatmentStopCreate(reason="Mala tolerancia"),
            )
        async with factory() as session:
            service = HospitalizationTreatmentService(session, DOCTOR)
            with pytest.raises(DomainError) as error:
                await service.update(
                    hospitalization_id,
                    entry_id,
                    TreatmentUpdate(description="Dipirona", dose="2 g"),
                )
            # Cerrarla de nuevo no rompe ni pisa el motivo.
            again = await service.stop(
                hospitalization_id,
                entry_id,
                TreatmentStopCreate(reason="Otro motivo"),
            )
            return error.value.status_code, again.status, again.end_reason

    status_code, status, reason = run_db(case)

    assert status_code == 409
    assert status == TreatmentStatus.SUSPENDED
    assert reason == "Mala tolerancia"


def test_an_indication_cannot_end_before_it_starts():
    async def case(factory):
        _, hospitalization_id = await admitted(factory)
        async with factory() as session:
            entry = await HospitalizationTreatmentService(session, DOCTOR).add(
                hospitalization_id,
                TreatmentCreate(description="Oxigeno", frequency="continuo"),
            )
            entry_id = entry.id
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationTreatmentService(session, DOCTOR).stop(
                    hospitalization_id,
                    entry_id,
                    TreatmentStopCreate(ended_at=datetime.now(UTC) - timedelta(days=1)),
                )
            return error.value.status_code

    assert run_db(case) == 422


def test_the_notes_record_who_attended_the_patient():
    async def case(factory):
        scenario, hospitalization_id = await admitted(factory)
        async with factory() as session:
            service = HospitalizationNoteService(session, DOCTOR)
            await service.add(
                hospitalization_id,
                ClinicalNoteCreate(note="Paciente afebril, buena evolucion."),
            )
            await service.add(
                hospitalization_id,
                ClinicalNoteCreate(
                    kind=ClinicalNoteKind.INTERCONSULTATION,
                    note="Cardiologia: sin indicacion de estudios por ahora.",
                    author_id=scenario.practitioner_id,
                    service_id=scenario.other_service_id,
                ),
            )
        async with factory() as check:
            notes = await HospitalizationNoteService(check).list_for_hospitalization(
                hospitalization_id
            )
            return [
                (note.kind, note.author_id is not None, note.service_id is not None)
                for note in notes
            ]

    notes = run_db(case)

    # Lo ultimo arriba.
    assert notes[0] == (ClinicalNoteKind.INTERCONSULTATION, True, True)
    assert notes[1] == (ClinicalNoteKind.EVOLUTION, False, False)


def test_a_note_loaded_by_mistake_is_voided_and_stays():
    async def case(factory):
        _, hospitalization_id = await admitted(factory)
        async with factory() as session:
            note = await HospitalizationNoteService(session, NURSE).add(
                hospitalization_id,
                ClinicalNoteCreate(
                    kind=ClinicalNoteKind.NURSING,
                    note="Nota del paciente equivocado.",
                ),
            )
            note_id = note.id
        async with factory() as session:
            await HospitalizationNoteService(session, NURSE).void(
                hospitalization_id,
                note_id,
                ClinicalNoteVoidCreate(reason="Cargada en el paciente equivocado"),
            )
        async with factory() as check:
            service = HospitalizationNoteService(check)
            everything = await service.list_for_hospitalization(hospitalization_id)
            visible = await service.list_for_hospitalization(
                hospitalization_id, include_void=False
            )
            return everything[0].status, everything[0].void_reason, len(visible)

    status, reason, visible = run_db(case)

    assert status == ClinicalNoteStatus.VOID
    assert reason == "Cargada en el paciente equivocado"
    assert visible == 0


def test_after_the_medical_discharge_only_an_admin_writes():
    async def case(factory):
        _, hospitalization_id = await admitted(factory)
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as session:
            with pytest.raises(DomainError) as treatment_error:
                await HospitalizationTreatmentService(session, DOCTOR).add(
                    hospitalization_id,
                    TreatmentCreate(description="Ibuprofeno"),
                )
        async with factory() as session:
            with pytest.raises(DomainError) as note_error:
                await HospitalizationNoteService(session, DOCTOR).add(
                    hospitalization_id,
                    ClinicalNoteCreate(note="Evolucion tardia."),
                )
        async with factory() as session:
            note = await HospitalizationNoteService(session, ADMIN).add(
                hospitalization_id,
                ClinicalNoteCreate(note="Resultado que llego despues del alta."),
            )
            return treatment_error.value.status_code, note_error.value.status_code, note.note

    treatment_status, note_status, note = run_db(case)

    assert treatment_status == 403
    assert note_status == 403
    assert note.startswith("Resultado")
