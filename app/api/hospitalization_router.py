"""Hospitalization lifecycle endpoints: responsible service, care team, discharge,
audit trail and account."""

import uuid

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.api.presenters import account_read
from app.schemas.domain import AdministrativeDischargeCreate, HospitalizationRead
from app.schemas.workflow import (
    AccountCloseCreate,
    AccountRead,
    CareTeamMemberCreate,
    CareTeamMemberRead,
    CareTeamRead,
    ChargeItemCreate,
    ChargeItemRead,
    ChargeItemVoidCreate,
    ClinicalDischargeCreate,
    DischargePlanCreate,
    DischargePlanRead,
    DischargeRead,
    HospitalizationEventRead,
    PhysicalDepartureCreate,
    ServiceAssignmentCreate,
    ServiceAssignmentRead,
)
from app.services.account import AccountService
from app.services.audit import list_events
from app.services.hospitalization import HospitalizationService

router = APIRouter(tags=["hospitalization-workflow"])


@router.get("/hospitalizations/{hospitalization_id}", response_model=HospitalizationRead)
async def get_hospitalization(hospitalization_id: uuid.UUID, session: DbSession):
    return await HospitalizationService(session).get(hospitalization_id)


@router.get(
    "/hospitalizations/{hospitalization_id}/service-assignments",
    response_model=list[ServiceAssignmentRead],
)
async def list_service_assignments(hospitalization_id: uuid.UUID, session: DbSession):
    return await HospitalizationService(session).list_service_assignments(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/service-assignments",
    response_model=ServiceAssignmentRead,
    status_code=201,
)
async def assign_service(
    hospitalization_id: uuid.UUID,
    payload: ServiceAssignmentCreate,
    session: DbSession,
):
    """Change the responsible service keeping the previous assignment as history."""

    return await HospitalizationService(session).assign_service(hospitalization_id, payload)


@router.get("/hospitalizations/{hospitalization_id}/care-team", response_model=CareTeamRead)
async def get_care_team(hospitalization_id: uuid.UUID, session: DbSession):
    return await HospitalizationService(session).care_team(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/care-team/members",
    response_model=CareTeamMemberRead,
    status_code=201,
)
async def add_care_team_member(
    hospitalization_id: uuid.UUID,
    payload: CareTeamMemberCreate,
    session: DbSession,
):
    return await HospitalizationService(session).add_care_team_member(hospitalization_id, payload)


@router.post(
    "/hospitalizations/{hospitalization_id}/care-team/members/{member_id}/end",
    response_model=CareTeamMemberRead,
)
async def end_care_team_member(
    hospitalization_id: uuid.UUID,
    member_id: uuid.UUID,
    session: DbSession,
):
    """End a participation. Membership history is closed, never deleted."""

    return await HospitalizationService(session).end_care_team_member(
        hospitalization_id,
        member_id,
    )


@router.get(
    "/hospitalizations/{hospitalization_id}/discharge-plans",
    response_model=list[DischargePlanRead],
)
async def list_discharge_plans(hospitalization_id: uuid.UUID, session: DbSession):
    return await HospitalizationService(session).discharge_plans(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/discharge-plans",
    response_model=DischargePlanRead,
    status_code=201,
)
async def plan_discharge(
    hospitalization_id: uuid.UUID,
    payload: DischargePlanCreate,
    session: DbSession,
):
    """Plan the discharge. The bed stays occupied and the hospitalization active."""

    return await HospitalizationService(session).plan_discharge(hospitalization_id, payload)


@router.get("/hospitalizations/{hospitalization_id}/discharge", response_model=DischargeRead)
async def get_discharge(hospitalization_id: uuid.UUID, session: DbSession):
    return await HospitalizationService(session).discharge(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/clinical-discharge",
    response_model=DischargeRead,
    status_code=201,
)
async def clinical_discharge(
    hospitalization_id: uuid.UUID,
    payload: ClinicalDischargeCreate,
    session: DbSession,
):
    """Clinical discharge. The bed remains OCCUPIED until the patient physically leaves."""

    return await HospitalizationService(session).clinical_discharge(hospitalization_id, payload)


@router.post(
    "/hospitalizations/{hospitalization_id}/physical-departure",
    response_model=HospitalizationRead,
)
async def physical_departure(
    hospitalization_id: uuid.UUID,
    payload: PhysicalDepartureCreate,
    session: DbSession,
):
    """The patient leaves the bed: the assignment ends and the bed goes to cleaning."""

    service = HospitalizationService(session)
    await service.physical_departure(hospitalization_id, payload)
    return await service.get(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/administrative-discharge",
    response_model=HospitalizationRead,
)
async def administrative_discharge(
    hospitalization_id: uuid.UUID,
    payload: AdministrativeDischargeCreate,
    session: DbSession,
):
    """Administrative discharge. Billing continues on its own afterwards."""

    return await HospitalizationService(session).administrative_discharge(
        hospitalization_id,
        payload,
    )


@router.get(
    "/hospitalizations/{hospitalization_id}/events",
    response_model=list[HospitalizationEventRead],
)
async def list_hospitalization_events(hospitalization_id: uuid.UUID, session: DbSession):
    await HospitalizationService(session).get(hospitalization_id)
    return await list_events(session, hospitalization_id)


@router.get("/hospitalizations/{hospitalization_id}/account", response_model=AccountRead)
async def get_account(hospitalization_id: uuid.UUID, session: DbSession):
    account = await AccountService(session).for_hospitalization(hospitalization_id)
    return account_read(account)


@router.post(
    "/hospitalizations/{hospitalization_id}/account/charge-items",
    response_model=ChargeItemRead,
    status_code=201,
)
async def add_charge_item(
    hospitalization_id: uuid.UUID,
    payload: ChargeItemCreate,
    session: DbSession,
):
    return await AccountService(session).add_charge_item(hospitalization_id, payload)


@router.post(
    "/hospitalizations/{hospitalization_id}/account/charge-items/{charge_item_id}/void",
    response_model=ChargeItemRead,
)
async def void_charge_item(
    hospitalization_id: uuid.UUID,
    charge_item_id: uuid.UUID,
    payload: ChargeItemVoidCreate,
    session: DbSession,
):
    """Anula un cargo de la cuenta. El cargo queda registrado y deja de sumar al total."""

    return await AccountService(session).void_charge_item(
        hospitalization_id,
        charge_item_id,
        payload,
    )


@router.post("/accounts/{account_id}/close", response_model=AccountRead)
async def close_account(
    account_id: uuid.UUID,
    payload: AccountCloseCreate,
    session: DbSession,
):
    """Financial closure: closes the account and the hospitalization."""

    service = AccountService(session)
    account = await service.close(account_id, actor=payload.actor)
    return account_read(await service.for_hospitalization(account.hospitalization_id))
