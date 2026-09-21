"""Medicación, tratamiento y notas de evolución de la internación."""

import uuid

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.treatment import (
    AdministrationCreate,
    AdministrationRead,
    AdministrationVoidCreate,
    ClinicalNoteCreate,
    ClinicalNoteRead,
    ClinicalNoteVoidCreate,
    TreatmentCreate,
    TreatmentRead,
    TreatmentStopCreate,
    TreatmentUpdate,
)
from app.services.treatment import (
    HospitalizationNoteService,
    HospitalizationTreatmentService,
    TreatmentAdministrationService,
)

router = APIRouter(tags=["treatments"])


@router.get(
    "/hospitalizations/{hospitalization_id}/treatments",
    response_model=list[TreatmentRead],
)
async def list_treatments(
    hospitalization_id: uuid.UUID,
    session: DbSession,
    only_active: bool = False,
):
    """Medicación y tratamientos de la internación; primero lo que se está dando ahora."""

    return await HospitalizationTreatmentService(session).list_for_hospitalization(
        hospitalization_id,
        only_active=only_active,
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/treatments",
    response_model=TreatmentRead,
    status_code=201,
)
async def add_treatment(
    hospitalization_id: uuid.UUID,
    payload: TreatmentCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Indica medicación o un tratamiento en curso.

    Con el alta médica dada la internación no recibe más cambios, salvo de un administrador.
    """

    return await HospitalizationTreatmentService(session, user).add(hospitalization_id, payload)


@router.put(
    "/hospitalizations/{hospitalization_id}/treatments/{treatment_id}",
    response_model=TreatmentRead,
)
async def update_treatment(
    hospitalization_id: uuid.UUID,
    treatment_id: uuid.UUID,
    payload: TreatmentUpdate,
    session: DbSession,
    user: CurrentUser,
):
    """Corrige la indicación en curso. Una ya cerrada no se edita: se indica de nuevo."""

    return await HospitalizationTreatmentService(session, user).update(
        hospitalization_id,
        treatment_id,
        payload,
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/treatments/{treatment_id}/stop",
    response_model=TreatmentRead,
)
async def stop_treatment(
    hospitalization_id: uuid.UUID,
    treatment_id: uuid.UUID,
    payload: TreatmentStopCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Corta lo que se estaba dando: suspendido antes de tiempo o cumplido."""

    return await HospitalizationTreatmentService(session, user).stop(
        hospitalization_id,
        treatment_id,
        payload,
    )


@router.get(
    "/hospitalizations/{hospitalization_id}/treatments/{treatment_id}/administrations",
    response_model=list[AdministrationRead],
)
async def list_administrations(
    hospitalization_id: uuid.UUID,
    treatment_id: uuid.UUID,
    session: DbSession,
):
    """Las tomas registradas de una indicación, la última arriba."""

    return await TreatmentAdministrationService(session).list_for_treatment(
        hospitalization_id,
        treatment_id,
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/treatments/{treatment_id}/administrations",
    response_model=AdministrationRead,
    status_code=201,
)
async def register_administration(
    hospitalization_id: uuid.UUID,
    treatment_id: uuid.UUID,
    payload: AdministrationCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Registra una toma: dada, o no dada con su motivo.

    Sin dosis toma la de la indicación, que es lo que se da habitualmente.
    """

    return await TreatmentAdministrationService(session, user).register(
        hospitalization_id,
        treatment_id,
        payload,
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/treatments/{treatment_id}"
    "/administrations/{administration_id}/void",
    response_model=AdministrationRead,
)
async def void_administration(
    hospitalization_id: uuid.UUID,
    treatment_id: uuid.UUID,
    administration_id: uuid.UUID,
    payload: AdministrationVoidCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Anula una toma cargada por error; queda registrada como anulada."""

    return await TreatmentAdministrationService(session, user).void(
        hospitalization_id,
        treatment_id,
        administration_id,
        payload,
    )


@router.get(
    "/hospitalizations/{hospitalization_id}/notes",
    response_model=list[ClinicalNoteRead],
)
async def list_notes(
    hospitalization_id: uuid.UUID,
    session: DbSession,
    include_void: bool = True,
):
    """Evoluciones, observaciones e interconsultas, lo último arriba."""

    return await HospitalizationNoteService(session).list_for_hospitalization(
        hospitalization_id,
        include_void=include_void,
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/notes",
    response_model=ClinicalNoteRead,
    status_code=201,
)
async def add_note(
    hospitalization_id: uuid.UUID,
    payload: ClinicalNoteCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Escribe una evolución, una observación o la atención de otro médico."""

    return await HospitalizationNoteService(session, user).add(hospitalization_id, payload)


@router.post(
    "/hospitalizations/{hospitalization_id}/notes/{note_id}/void",
    response_model=ClinicalNoteRead,
)
async def void_note(
    hospitalization_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: ClinicalNoteVoidCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Anula una nota cargada por error; el texto queda en la historia."""

    return await HospitalizationNoteService(session, user).void(
        hospitalization_id,
        note_id,
        payload,
    )
