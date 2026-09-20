"""Recetas e indicaciones del alta, y su impresión."""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.prescription import (
    DischargePrescriptionCreate,
    DischargePrescriptionRead,
    DischargePrescriptionUpdate,
)
from app.services.prescription import DischargePrescriptionService, build_document
from app.services.prescription_pdf import render

router = APIRouter(tags=["prescriptions"])


@router.get(
    "/hospitalizations/{hospitalization_id}/discharge-prescriptions",
    response_model=list[DischargePrescriptionRead],
)
async def list_discharge_prescriptions(hospitalization_id: uuid.UUID, session: DbSession):
    """Lo que el paciente se lleva indicado: medicación y prácticas."""

    return await DischargePrescriptionService(session).list_for_hospitalization(
        hospitalization_id
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/discharge-prescriptions",
    response_model=DischargePrescriptionRead,
    status_code=201,
)
async def add_discharge_prescription(
    hospitalization_id: uuid.UUID,
    payload: DischargePrescriptionCreate,
    session: DbSession,
    user: CurrentUser,
):
    return await DischargePrescriptionService(session, user).add(hospitalization_id, payload)


@router.put(
    "/hospitalizations/{hospitalization_id}/discharge-prescriptions/{prescription_id}",
    response_model=DischargePrescriptionRead,
)
async def update_discharge_prescription(
    hospitalization_id: uuid.UUID,
    prescription_id: uuid.UUID,
    payload: DischargePrescriptionUpdate,
    session: DbSession,
    user: CurrentUser,
):
    return await DischargePrescriptionService(session, user).update(
        hospitalization_id, prescription_id, payload
    )


@router.delete(
    "/hospitalizations/{hospitalization_id}/discharge-prescriptions/{prescription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_discharge_prescription(
    hospitalization_id: uuid.UUID,
    prescription_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
):
    await DischargePrescriptionService(session, user).remove(hospitalization_id, prescription_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/hospitalizations/{hospitalization_id}/discharge-prescriptions/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF para imprimir"}},
)
async def print_discharge_prescriptions(hospitalization_id: uuid.UUID, session: DbSession):
    """Receta e indicación de prácticas en un PDF, una hoja cada una."""

    document = await build_document(session, hospitalization_id)
    pdf = render(document)
    filename = quote(f"indicaciones-{document.patient_name}.pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )
