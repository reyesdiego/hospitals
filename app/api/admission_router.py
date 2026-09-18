"""Authorization endpoints for admission requests and hospitalizations."""

import uuid

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.schemas.workflow import (
    AuthorizationRead,
    AuthorizationRequestCreate,
    AuthorizationResolveCreate,
)
from app.services.authorization import AuthorizationService

router = APIRouter(tags=["authorizations"])


@router.get("/admissions/{admission_id}/authorizations", response_model=list[AuthorizationRead])
async def list_admission_authorizations(admission_id: uuid.UUID, session: DbSession):
    return await AuthorizationService(session).list_for_admission(admission_id)


@router.post(
    "/admissions/{admission_id}/authorizations",
    response_model=AuthorizationRead,
    status_code=201,
)
async def request_admission_authorization(
    admission_id: uuid.UUID,
    payload: AuthorizationRequestCreate,
    session: DbSession,
):
    return await AuthorizationService(session).request_for_admission(admission_id, payload)


@router.post("/authorizations/{authorization_id}/resolve", response_model=AuthorizationRead)
async def resolve_authorization(
    authorization_id: uuid.UUID,
    payload: AuthorizationResolveCreate,
    session: DbSession,
):
    """Record the payer answer; an authorized admission moves on to the bed search."""

    return await AuthorizationService(session).resolve(authorization_id, payload)


@router.get(
    "/hospitalizations/{hospitalization_id}/authorizations",
    response_model=list[AuthorizationRead],
)
async def list_hospitalization_authorizations(hospitalization_id: uuid.UUID, session: DbSession):
    return await AuthorizationService(session).list_for_hospitalization(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/authorizations",
    response_model=AuthorizationRead,
    status_code=201,
)
async def request_hospitalization_authorization(
    hospitalization_id: uuid.UUID,
    payload: AuthorizationRequestCreate,
    session: DbSession,
):
    return await AuthorizationService(session).request_for_hospitalization(
        hospitalization_id,
        payload,
    )
