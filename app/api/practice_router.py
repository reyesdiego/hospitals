"""Medical practice catalog (nomenclador) endpoints."""

import uuid
from datetime import date

from fastapi import APIRouter, Response, status

from app.api.dependencies import DbSession
from app.api.presenters import hospitalization_practice_read
from app.models.practice import Nomenclador, PracticeChapter, PracticeSetting, PracticeType
from app.schemas.practice import (
    HospitalizationPracticeCancelCreate,
    HospitalizationPracticeCreate,
    HospitalizationPracticePerformCreate,
    HospitalizationPracticeRead,
    MedicalPracticeCreate,
    MedicalPracticeRead,
    MedicalPracticeTariffCreate,
    MedicalPracticeTariffRead,
    MedicalPracticeTariffUpdate,
    MedicalPracticeUpdate,
)
from app.services.practice import HospitalizationPracticeService, MedicalPracticeService

router = APIRouter(tags=["practices"])


@router.get("/practices", response_model=list[MedicalPracticeRead])
async def list_practices(
    session: DbSession,
    nomenclador: Nomenclador | None = None,
    chapter: PracticeChapter | None = None,
    practice_type: PracticeType | None = None,
    setting: PracticeSetting | None = None,
    search: str | None = None,
    only_active: bool = False,
):
    """Catálogo de prácticas. ``search`` busca por código o nombre."""

    return await MedicalPracticeService(session).list_practices(
        nomenclador=nomenclador,
        chapter=chapter,
        practice_type=practice_type,
        setting=setting,
        search=search,
        only_active=only_active,
    )


@router.post("/practices", response_model=MedicalPracticeRead, status_code=201)
async def create_practice(payload: MedicalPracticeCreate, session: DbSession):
    return await MedicalPracticeService(session).create(payload)


@router.get("/practices/{practice_id}", response_model=MedicalPracticeRead)
async def get_practice(practice_id: uuid.UUID, session: DbSession):
    return await MedicalPracticeService(session).get(practice_id)


@router.put("/practices/{practice_id}", response_model=MedicalPracticeRead)
async def update_practice(
    practice_id: uuid.UUID,
    payload: MedicalPracticeUpdate,
    session: DbSession,
):
    return await MedicalPracticeService(session).update(practice_id, payload)


@router.delete("/practices/{practice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_practice(practice_id: uuid.UUID, session: DbSession):
    await MedicalPracticeService(session).delete(practice_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/practices/{practice_id}/tariffs",
    response_model=list[MedicalPracticeTariffRead],
)
async def list_practice_tariffs(
    practice_id: uuid.UUID,
    session: DbSession,
    payer_id: uuid.UUID | None = None,
):
    return await MedicalPracticeService(session).list_tariffs(practice_id, payer_id=payer_id)


@router.get(
    "/practices/{practice_id}/tariffs/effective",
    response_model=MedicalPracticeTariffRead,
)
async def get_effective_practice_tariff(
    practice_id: uuid.UUID,
    session: DbSession,
    payer_id: uuid.UUID | None = None,
    health_plan_id: uuid.UUID | None = None,
    on: date | None = None,
):
    """Valor vigente de la práctica: primero el del plan, luego el del financiador y
    por último el institucional."""

    return await MedicalPracticeService(session).effective_tariff(
        practice_id,
        payer_id=payer_id,
        health_plan_id=health_plan_id,
        on=on,
    )


@router.post(
    "/practices/{practice_id}/tariffs",
    response_model=MedicalPracticeTariffRead,
    status_code=201,
)
async def create_practice_tariff(
    practice_id: uuid.UUID,
    payload: MedicalPracticeTariffCreate,
    session: DbSession,
):
    return await MedicalPracticeService(session).create_tariff(practice_id, payload)


@router.put(
    "/practices/{practice_id}/tariffs/{tariff_id}",
    response_model=MedicalPracticeTariffRead,
)
async def update_practice_tariff(
    practice_id: uuid.UUID,
    tariff_id: uuid.UUID,
    payload: MedicalPracticeTariffUpdate,
    session: DbSession,
):
    return await MedicalPracticeService(session).update_tariff(practice_id, tariff_id, payload)


@router.delete(
    "/practices/{practice_id}/tariffs/{tariff_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_practice_tariff(
    practice_id: uuid.UUID,
    tariff_id: uuid.UUID,
    session: DbSession,
):
    await MedicalPracticeService(session).delete_tariff(practice_id, tariff_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/hospitalizations/{hospitalization_id}/practices",
    response_model=list[HospitalizationPracticeRead],
)
async def list_hospitalization_practices(hospitalization_id: uuid.UUID, session: DbSession):
    """Prácticas indicadas en la internación, con el cargo que generó cada una."""

    orders = await HospitalizationPracticeService(session).list_for_hospitalization(
        hospitalization_id
    )
    return [await hospitalization_practice_read(session, order) for order in orders]


@router.post(
    "/hospitalizations/{hospitalization_id}/practices",
    response_model=HospitalizationPracticeRead,
    status_code=201,
)
async def register_hospitalization_practice(
    hospitalization_id: uuid.UUID,
    payload: HospitalizationPracticeCreate,
    session: DbSession,
):
    """Registra una práctica y el profesional que la indicó. Si se informa
    ``performed_at`` queda como realizada y se carga a la cuenta de la internación."""

    order = await HospitalizationPracticeService(session).register(hospitalization_id, payload)
    return await hospitalization_practice_read(session, order)


@router.post(
    "/hospitalizations/{hospitalization_id}/practices/{order_id}/perform",
    response_model=HospitalizationPracticeRead,
)
async def perform_hospitalization_practice(
    hospitalization_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: HospitalizationPracticePerformCreate,
    session: DbSession,
):
    """La realización es la que genera el cargo, con el valor vigente de la práctica
    para la cobertura de la internación."""

    order = await HospitalizationPracticeService(session).perform(
        hospitalization_id,
        order_id,
        payload,
    )
    return await hospitalization_practice_read(session, order)


@router.post(
    "/hospitalizations/{hospitalization_id}/practices/{order_id}/cancel",
    response_model=HospitalizationPracticeRead,
)
async def cancel_hospitalization_practice(
    hospitalization_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: HospitalizationPracticeCancelCreate,
    session: DbSession,
):
    """Anula una práctica indicada y todavía no realizada."""

    order = await HospitalizationPracticeService(session).cancel(
        hospitalization_id,
        order_id,
        payload,
    )
    return await hospitalization_practice_read(session, order)
