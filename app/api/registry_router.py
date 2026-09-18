"""Patient identity registry and coverage catalog endpoints."""

import uuid

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.models.patient import PatientIdentifierType
from app.schemas.domain import PatientCoverageCreate, PatientCoverageRead, PatientRead
from app.schemas.workflow import (
    HealthPlanCreate,
    HealthPlanRead,
    PatientContactCreate,
    PatientContactRead,
    PatientIdentifierCreate,
    PatientIdentifierRead,
    PatientMatchRead,
    PayerCreate,
    PayerRead,
)
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
async def list_payers(session: DbSession):
    return await CoverageService(session).list_payers()


@router.post("/payers", response_model=PayerRead, status_code=201)
async def create_payer(payload: PayerCreate, session: DbSession):
    return await CoverageService(session).create_payer(payload)


@router.get("/payers/{payer_id}/health-plans", response_model=list[HealthPlanRead])
async def list_health_plans(payer_id: uuid.UUID, session: DbSession):
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
