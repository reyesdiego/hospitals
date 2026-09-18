"""Patient identity registry and coverage catalog endpoints."""

import uuid

from fastapi import APIRouter, Response, status

from app.api.dependencies import DbSession
from app.api.presenters import health_plan_practice_read
from app.models.patient import PatientIdentifierType
from app.models.practice import PracticeChapter
from app.schemas.domain import (
    PatientCoverageCreate,
    PatientCoverageRead,
    PatientCoverageUpdate,
    PatientRead,
)
from app.schemas.practice import (
    HealthPlanPracticeBulkCreate,
    HealthPlanPracticeBulkRead,
    HealthPlanPracticeCreate,
    HealthPlanPracticeRead,
    HealthPlanPracticeUpdate,
)
from app.schemas.workflow import (
    HealthPlanCreate,
    HealthPlanRead,
    HealthPlanUpdate,
    PatientContactCreate,
    PatientContactRead,
    PatientIdentifierCreate,
    PatientIdentifierRead,
    PatientMatchRead,
    PayerCreate,
    PayerRead,
    PayerUpdate,
)
from app.services.plan_coverage import HealthPlanPracticeService
from app.services.registry import CoverageService, PatientRegistryService

router = APIRouter(tags=["registry"])


@router.get("/patients/search", response_model=list[PatientMatchRead])
async def search_patients(
    value: str,
    session: DbSession,
    identifier_type: PatientIdentifierType | None = None,
):
    """Search identifiers before creating a patient, to reduce duplicates."""

    matches = await PatientRegistryService(session).search_patients(
        value=value,
        identifier_type=identifier_type,
    )
    return [
        PatientMatchRead(patient=PatientRead.model_validate(patient), matched_on=matched_on)
        for patient, matched_on in matches
    ]


@router.get("/patients/{patient_id}/identifiers", response_model=list[PatientIdentifierRead])
async def list_patient_identifiers(patient_id: uuid.UUID, session: DbSession):
    return await PatientRegistryService(session).list_identifiers(patient_id)


@router.post(
    "/patients/{patient_id}/identifiers",
    response_model=PatientIdentifierRead,
    status_code=201,
)
async def create_patient_identifier(
    patient_id: uuid.UUID,
    payload: PatientIdentifierCreate,
    session: DbSession,
):
    return await PatientRegistryService(session).add_identifier(patient_id, payload)


@router.get("/patients/{patient_id}/contacts", response_model=list[PatientContactRead])
async def list_patient_contacts(patient_id: uuid.UUID, session: DbSession):
    return await PatientRegistryService(session).list_contacts(patient_id)


@router.post("/patients/{patient_id}/contacts", response_model=PatientContactRead, status_code=201)
async def create_patient_contact(
    patient_id: uuid.UUID,
    payload: PatientContactCreate,
    session: DbSession,
):
    return await PatientRegistryService(session).add_contact(patient_id, payload)


@router.get("/payers", response_model=list[PayerRead])
async def list_payers(session: DbSession, search: str | None = None):
    """Catálogo de financiadores. ``search`` busca por nombre o código."""

    return await CoverageService(session).list_payers(search=search)


@router.post("/payers", response_model=PayerRead, status_code=201)
async def create_payer(payload: PayerCreate, session: DbSession):
    return await CoverageService(session).create_payer(payload)


@router.get("/payers/{payer_id}", response_model=PayerRead)
async def get_payer(payer_id: uuid.UUID, session: DbSession):
    return await CoverageService(session).get_payer(payer_id)


@router.put("/payers/{payer_id}", response_model=PayerRead)
async def update_payer(payer_id: uuid.UUID, payload: PayerUpdate, session: DbSession):
    return await CoverageService(session).update_payer(payer_id, payload)


@router.delete("/payers/{payer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payer(payer_id: uuid.UUID, session: DbSession):
    await CoverageService(session).delete_payer(payer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/payers/{payer_id}/health-plans", response_model=list[HealthPlanRead])
async def list_payer_health_plans(payer_id: uuid.UUID, session: DbSession):
    return await CoverageService(session).list_health_plans(payer_id)


@router.post(
    "/payers/{payer_id}/health-plans",
    response_model=HealthPlanRead,
    status_code=201,
)
async def create_health_plan(
    payer_id: uuid.UUID,
    payload: HealthPlanCreate,
    session: DbSession,
):
    return await CoverageService(session).create_health_plan(payer_id, payload)


@router.get("/health-plans", response_model=list[HealthPlanRead])
async def list_health_plans(session: DbSession, payer_id: uuid.UUID | None = None):
    return await CoverageService(session).list_health_plans(payer_id)


@router.get("/health-plans/{health_plan_id}", response_model=HealthPlanRead)
async def get_health_plan(health_plan_id: uuid.UUID, session: DbSession):
    return await CoverageService(session).get_health_plan(health_plan_id)


@router.put("/health-plans/{health_plan_id}", response_model=HealthPlanRead)
async def update_health_plan(
    health_plan_id: uuid.UUID,
    payload: HealthPlanUpdate,
    session: DbSession,
):
    return await CoverageService(session).update_health_plan(health_plan_id, payload)


@router.delete("/health-plans/{health_plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_health_plan(health_plan_id: uuid.UUID, session: DbSession):
    await CoverageService(session).delete_health_plan(health_plan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/health-plans/{health_plan_id}/practices",
    response_model=list[HealthPlanPracticeRead],
)
async def list_health_plan_practices(
    health_plan_id: uuid.UUID,
    session: DbSession,
    chapter: PracticeChapter | None = None,
    search: str | None = None,
    only_covered: bool = False,
):
    """Cartilla del plan: las prácticas que tiene cargadas y en qué condiciones."""

    entries = await HealthPlanPracticeService(session).list_practices(
        health_plan_id,
        chapter=chapter,
        search=search,
        only_covered=only_covered,
    )
    return [health_plan_practice_read(entry) for entry in entries]


@router.post(
    "/health-plans/{health_plan_id}/practices",
    response_model=HealthPlanPracticeRead,
    status_code=201,
)
async def link_health_plan_practice(
    health_plan_id: uuid.UUID,
    payload: HealthPlanPracticeCreate,
    session: DbSession,
):
    entry = await HealthPlanPracticeService(session).link(health_plan_id, payload)
    return health_plan_practice_read(entry)


@router.post(
    "/health-plans/{health_plan_id}/practices/bulk",
    response_model=HealthPlanPracticeBulkRead,
    status_code=201,
)
async def link_health_plan_practices(
    health_plan_id: uuid.UUID,
    payload: HealthPlanPracticeBulkCreate,
    session: DbSession,
):
    """Alta masiva. Las que ya estaban en la cartilla se devuelven como omitidas: sus
    condiciones no se pisan."""

    created, skipped = await HealthPlanPracticeService(session).link_many(health_plan_id, payload)
    return HealthPlanPracticeBulkRead(
        created=[health_plan_practice_read(entry) for entry in created],
        skipped_practice_ids=skipped,
    )


@router.put(
    "/health-plans/{health_plan_id}/practices/{plan_practice_id}",
    response_model=HealthPlanPracticeRead,
)
async def update_health_plan_practice(
    health_plan_id: uuid.UUID,
    plan_practice_id: uuid.UUID,
    payload: HealthPlanPracticeUpdate,
    session: DbSession,
):
    entry = await HealthPlanPracticeService(session).update(
        health_plan_id, plan_practice_id, payload
    )
    return health_plan_practice_read(entry)


@router.delete(
    "/health-plans/{health_plan_id}/practices/{plan_practice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_health_plan_practice(
    health_plan_id: uuid.UUID,
    plan_practice_id: uuid.UUID,
    session: DbSession,
):
    """Saca la práctica de la cartilla. Para dejar asentado que el plan no la cubre, marcarla
    como no cubierta en lugar de borrarla."""

    await HealthPlanPracticeService(session).unlink(health_plan_id, plan_practice_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/patients/{patient_id}/coverages", response_model=list[PatientCoverageRead])
async def list_patient_coverages(patient_id: uuid.UUID, session: DbSession):
    return await CoverageService(session).list_coverages(patient_id)


@router.post(
    "/patients/{patient_id}/coverages",
    response_model=PatientCoverageRead,
    status_code=201,
)
async def create_patient_coverage(
    patient_id: uuid.UUID,
    payload: PatientCoverageCreate,
    session: DbSession,
):
    return await CoverageService(session).create_coverage(patient_id, payload)


@router.get("/coverages/{coverage_id}", response_model=PatientCoverageRead)
async def get_coverage(coverage_id: uuid.UUID, session: DbSession):
    return await CoverageService(session).get_coverage(coverage_id)


@router.put("/coverages/{coverage_id}", response_model=PatientCoverageRead)
async def update_coverage(
    coverage_id: uuid.UUID,
    payload: PatientCoverageUpdate,
    session: DbSession,
):
    return await CoverageService(session).update_coverage(coverage_id, payload)


@router.delete("/coverages/{coverage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_coverage(coverage_id: uuid.UUID, session: DbSession):
    """Elimina una cobertura no utilizada; si ya tiene admisiones o cuentas, désela de baja
    cambiando su ``status`` a ``INACTIVE``."""

    await CoverageService(session).delete_coverage(coverage_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
