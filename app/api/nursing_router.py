"""Panel de enfermería: las tareas indicadas al paciente y su ejecución."""

import uuid
from datetime import date

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.api.presenters import hospitalization_practice_read, nursing_task_read
from app.schemas.practice import (
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticePerformCreate,
    HospitalizationPracticeRead,
    NursingTaskRead,
)
from app.services.nursing import NursingTaskService

router = APIRouter(tags=["nursing"])


@router.get("/nursing-tasks", response_model=list[NursingTaskRead])
async def list_nursing_tasks(
    session: DbSession,
    pending_only: bool = True,
    hospitalization_id: uuid.UUID | None = None,
    ward: str | None = None,
    on: date | None = None,
):
    """Lo que el médico indicó y enfermería todavía tiene que hacer.

    ``pending_only=false`` con ``on`` muestra además lo aplicado o cancelado ese día, que es
    lo que se revisa al cerrar un turno.
    """

    tasks = await NursingTaskService(session).worklist(
        pending_only=pending_only,
        hospitalization_id=hospitalization_id,
        ward=ward,
        on=on,
    )
    return [nursing_task_read(task) for task in tasks]


@router.post(
    "/nursing-tasks/{order_id}/perform",
    response_model=HospitalizationPracticeRead,
)
async def perform_nursing_task(
    order_id: uuid.UUID,
    payload: HospitalizationPracticePerformCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Marcar la tarea como aplicada: genera el cargo y queda en el historial."""

    order = await NursingTaskService(session, user).perform(order_id, payload)
    return await hospitalization_practice_read(session, order)


@router.post(
    "/nursing-tasks/{order_id}/cancel",
    response_model=HospitalizationPracticeRead,
)
async def cancel_nursing_task(
    order_id: uuid.UUID,
    payload: HospitalizationPracticeCancelCreate,
    session: DbSession,
    user: CurrentUser,
):
    """Cancelar la tarea, con el motivo por el que no se aplicó."""

    order = await NursingTaskService(session, user).cancel(order_id, payload)
    return await hospitalization_practice_read(session, order)
