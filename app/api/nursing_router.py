"""Panel de enfermería: las tareas indicadas al paciente y su ejecución."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.api.presenters import hospitalization_practice_read, nursing_task_read
from app.schemas.practice import (
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticePerformCreate,
    HospitalizationPracticeRead,
    NursingTaskRead,
)
from app.schemas.treatment import DoseSlotRead, MedicationRoundRead
from app.services.nursing import NursingTaskService
from app.services.treatment import TreatmentAdministrationService

router = APIRouter(tags=["nursing"])


@router.get("/nursing-tasks", response_model=list[NursingTaskRead])
async def list_nursing_tasks(
    session: DbSession,
    pending_only: bool = True,
    hospitalization_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None,
    ward: str | None = None,
    on: date | None = None,
):
    """Lo que el médico indicó y enfermería tiene que hacer, o ya hizo.

    - Sin parámetros: lo pendiente de las internaciones activas.
    - ``pending_only=false`` con ``on``: lo de ese día, para cerrar el turno.
    - ``pending_only=false`` sin ``on``: el historial, que incluye internaciones cerradas.

    ``patient_id`` y ``service_id`` acotan por paciente y por servicio responsable.
    """

    tasks = await NursingTaskService(session).worklist(
        pending_only=pending_only,
        hospitalization_id=hospitalization_id,
        patient_id=patient_id,
        service_id=service_id,
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


@router.get("/nursing-medications", response_model=list[MedicationRoundRead])
async def list_medication_round(
    session: DbSession,
    hospitalization_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None,
    ward: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    overdue_only: bool = False,
):
    """La vuelta de medicación: indicaciones activas de internaciones activas, con sus
    horarios calculados.

    Cada indicación trae la línea de tiempo de la ventana —lo que se dio, lo que se omitió
    y lo que falta—, el próximo horario y si está vencida. Sin ventana son las doce horas
    para atrás y las doce para adelante. Primero lo vencido.
    """

    rounds = await TreatmentAdministrationService(session).medication_round(
        hospitalization_id=hospitalization_id,
        service_id=service_id,
        ward=ward,
        window_start=window_start,
        window_end=window_end,
        overdue_only=overdue_only,
    )
    return [
        MedicationRoundRead(
            treatment_id=item.treatment.id,
            hospitalization_id=item.treatment.hospitalization_id,
            patient_id=item.patient.id,
            patient_name=f"{item.patient.last_name}, {item.patient.first_name}",
            ward=item.ward,
            room_code=item.room_code,
            bed_code=item.bed_code,
            service_id=item.service_id,
            service_name=item.service_name,
            kind=item.treatment.kind,
            description=item.treatment.description,
            presentation=item.treatment.presentation,
            dose=item.treatment.dose,
            route=item.treatment.route,
            frequency=item.treatment.frequency,
            schedule_kind=item.treatment.schedule_kind,
            interval_hours=item.treatment.interval_hours,
            times_of_day=item.treatment.times_of_day,
            started_at=item.treatment.started_at,
            last_administered_at=item.last_administered_at,
            administrations=item.administrations,
            next_due_at=item.next_due_at,
            overdue=item.overdue,
            slots=[
                DoseSlotRead(
                    due_at=slot.due_at,
                    state=slot.state.value,
                    administration_id=slot.administration_id,
                    dose=slot.dose,
                    reason=slot.reason,
                )
                for slot in item.slots
            ],
        )
        for item in rounds
    ]
