"""Catálogo CIE-10 de diagnósticos."""

import uuid

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, DbSession
from app.models.diagnosis import DiagnosisLevel, DiagnosisStage
from app.schemas.diagnosis import (
    DiagnosisCodeCreate,
    DiagnosisCodeRead,
    DiagnosisCodeUpdate,
    HospitalizationDiagnosisCreate,
    HospitalizationDiagnosisRead,
    HospitalizationDiagnosisUpdate,
)
from app.services.diagnosis import (
    DEFAULT_LIMIT,
    DiagnosisService,
    HospitalizationDiagnosisService,
)

router = APIRouter(tags=["diagnoses"])


@router.get("/diagnoses", response_model=list[DiagnosisCodeRead])
async def list_diagnoses(
    session: DbSession,
    search: str | None = None,
    chapter_code: str | None = None,
    parent_code: str | None = None,
    level: DiagnosisLevel | None = None,
    only_active: bool = False,
    only_codifiable: bool = False,
    limit: int = DEFAULT_LIMIT,
):
    """Catálogo CIE-10. ``search`` busca por código o por texto del diagnóstico.

    Son más de catorce mil códigos: la respuesta viene acotada por ``limit``.
    """

    service = DiagnosisService(session)
    entries = await service.list_codes(
        search=search,
        chapter_code=chapter_code,
        parent_code=parent_code,
        level=level,
        only_active=only_active,
        only_codifiable=only_codifiable,
        limit=limit,
    )
    children = await service.children_counts([entry.code for entry in entries])
    return [
        DiagnosisCodeRead.model_validate(entry).model_copy(
            update={"child_count": children.get(entry.code, 0)}
        )
        for entry in entries
    ]


@router.post("/diagnoses", response_model=DiagnosisCodeRead, status_code=201)
async def create_diagnosis(payload: DiagnosisCodeCreate, session: DbSession):
    return await DiagnosisService(session).create(payload)


@router.get("/diagnoses/by-code/{code}", response_model=DiagnosisCodeRead)
async def get_diagnosis_by_code(code: str, session: DbSession):
    """El código es la identidad del diagnóstico fuera del sistema."""

    return await DiagnosisService(session).get_by_code(code)


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisCodeRead)
async def get_diagnosis(diagnosis_id: uuid.UUID, session: DbSession):
    return await DiagnosisService(session).get(diagnosis_id)


@router.put("/diagnoses/{diagnosis_id}", response_model=DiagnosisCodeRead)
async def update_diagnosis(
    diagnosis_id: uuid.UUID,
    payload: DiagnosisCodeUpdate,
    session: DbSession,
):
    return await DiagnosisService(session).update(diagnosis_id, payload)


@router.delete("/diagnoses/{diagnosis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diagnosis(diagnosis_id: uuid.UUID, session: DbSession):
    """Para sacar de circulación un código que ya se usó, desactivarlo en lugar de
    borrarlo."""

    await DiagnosisService(session).delete(diagnosis_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/hospitalizations/{hospitalization_id}/diagnoses",
    response_model=list[HospitalizationDiagnosisRead],
)
async def list_hospitalization_diagnoses(
    hospitalization_id: uuid.UUID,
    session: DbSession,
    stage: DiagnosisStage | None = None,
):
    """Diagnósticos de la internación: los de ingreso y los de egreso."""

    return await HospitalizationDiagnosisService(session).list_for_hospitalization(
        hospitalization_id,
        stage=stage,
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/diagnoses",
    response_model=HospitalizationDiagnosisRead,
    status_code=201,
)
async def add_hospitalization_diagnosis(
    hospitalization_id: uuid.UUID,
    payload: HospitalizationDiagnosisCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Asienta un diagnóstico del catálogo CIE-10. Uno solo puede ser el principal de cada
    momento, y con el alta médica dada solo lo corrige un administrador."""

    return await HospitalizationDiagnosisService(session, user).add(hospitalization_id, payload)


@router.put(
    "/hospitalizations/{hospitalization_id}/diagnoses/{entry_id}",
    response_model=HospitalizationDiagnosisRead,
)
async def update_hospitalization_diagnosis(
    hospitalization_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: HospitalizationDiagnosisUpdate,
    session: DbSession,
    user: CurrentUser,
):
    """Corrige el rol, el profesional o las notas. Para cambiar el código, quítelo y
    asiente el que corresponde."""

    return await HospitalizationDiagnosisService(session, user).update(
        hospitalization_id,
        entry_id,
        payload,
    )


@router.delete(
    "/hospitalizations/{hospitalization_id}/diagnoses/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_hospitalization_diagnosis(
    hospitalization_id: uuid.UUID,
    entry_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
):
    await HospitalizationDiagnosisService(session, user).remove(hospitalization_id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
