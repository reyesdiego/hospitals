"""Admission, discharge and account lifecycle against PostgreSQL."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.exceptions import DomainError
from app.models.account import Account, AccountStatus
from app.models.admission import (
    Admission,
    AdmissionStatus,
    AuthorizationStatus,
    Episode,
    EpisodeStatus,
)
from app.models.audit import HospitalizationEvent, HospitalizationEventType
from app.models.authorization import Authorization, AuthorizationState
from app.models.bed import Bed, BedAssignment, BedStatus
from app.models.care_team import CareTeamRole
from app.models.discharge import DischargePlanStatus
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.schemas.domain import AdministrativeDischargeCreate, HospitalizationCreate
from app.schemas.workflow import (
    AuthorizationRequestCreate,
    AuthorizationResolveCreate,
    CareTeamMemberCreate,
    ChargeItemCreate,
    ClinicalDischargeCreate,
    DischargePlanCreate,
    PhysicalDepartureCreate,
    ServiceAssignmentCreate,
)
from app.services.account import AccountService
from app.services.admission import AdmissionWorkflowService
from app.services.authorization import AuthorizationService
from app.services.bed_assignment import BedAssignmentService
from app.services.hospitalization import HospitalizationService
from tests.conftest import requires_postgres, run_db
from tests.factories import admission_payload, build_scenario, hospitalization_from_admission

pytestmark = requires_postgres


async def admitted_hospitalization(factory, scenario):
    """Admission request confirmed on a bed: the patient is physically admitted."""

    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    return hospitalization_id


def test_admission_request_creates_the_whole_hospitalization_context():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission = await AdmissionWorkflowService(session).create(admission_payload(scenario))
            admission_id = admission.id
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            hospitalization = await check.get(Hospitalization, admission.hospitalization_id)
            episode = await check.get(Episode, admission.episode_id)
            account = await check.scalar(
                select(Account).where(Account.hospitalization_id == hospitalization.id)
            )
            services = await HospitalizationService(check).list_service_assignments(
                hospitalization.id
            )
            care_team = await HospitalizationService(check).care_team(hospitalization.id)
            events = list(
                (
                    await check.scalars(
                        select(HospitalizationEvent.event_type).where(
                            HospitalizationEvent.hospitalization_id == hospitalization.id
                        )
                    )
                ).all()
            )
            return admission, hospitalization, episode, account, services, care_team, events

    admission, hospitalization, episode, account, services, care_team, events = run_db(case)

    assert admission.status == AdmissionStatus.PENDING_BED
    assert admission.requested_at is not None
    assert hospitalization.status == HospitalizationStatus.PENDING_BED
    assert hospitalization.episode_id == episode.id
    assert hospitalization.facility_id is not None
    assert episode.status == EpisodeStatus.OPEN
    assert account.status == AccountStatus.OPEN
    assert len(services) == 1 and services[0].ended_at is None
    assert [member.role for member in care_team.members] == [CareTeamRole.ATTENDING_PHYSICIAN]
    assert HospitalizationEventType.ADMISSION_REQUESTED in events
    assert HospitalizationEventType.HOSPITALIZATION_CREATED in events
    assert HospitalizationEventType.SERVICE_ASSIGNED in events


def test_admission_request_with_requested_bed_confirms_the_admission():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission = await AdmissionWorkflowService(session).create(
                admission_payload(
                    scenario,
                    requested_bed_id=scenario.bed_ids[0],
                    confirm_admission=True,
                )
            )
            admission_id = admission.id
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            hospitalization = await check.get(Hospitalization, admission.hospitalization_id)
            bed = await check.get(Bed, scenario.bed_ids[0])
            return admission.status, hospitalization.status, hospitalization.admitted_at, bed.status

    status, hospitalization_status, admitted_at, bed_status = run_db(case)

    assert status == AdmissionStatus.ADMITTED
    assert hospitalization_status == HospitalizationStatus.IN_PROGRESS
    assert admitted_at is not None
    assert bed_status == BedStatus.OCCUPIED


def test_admission_request_requires_identity_validation():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await AdmissionWorkflowService(session).create(
                    admission_payload(scenario, identity_validated=False)
                )
            return error.value.status_code

    assert run_db(case) == 422


def test_authorization_decision_moves_the_admission_request():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission = await AdmissionWorkflowService(session).create(admission_payload(scenario))
            admission_id = admission.id
        async with factory() as session:
            authorization = await AuthorizationService(session).request_for_admission(
                admission_id,
                AuthorizationRequestCreate(requested_by="admision"),
            )
            authorization_id = authorization.id
        async with factory() as check:
            pending = await check.get(Admission, admission_id)
            pending_status = pending.status
        async with factory() as session:
            await AuthorizationService(session).resolve(
                authorization_id,
                AuthorizationResolveCreate(
                    status=AuthorizationState.AUTHORIZED,
                    authorization_number="AUT-9001",
                ),
            )
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            authorization = await check.get(Authorization, authorization_id)
            events = list(
                (
                    await check.scalars(
                        select(HospitalizationEvent.event_type).where(
                            HospitalizationEvent.admission_id == admission_id
                        )
                    )
                ).all()
            )
            return pending_status, admission, authorization, events

    pending_status, admission, authorization, events = run_db(case)

    assert pending_status == AdmissionStatus.PENDING_AUTHORIZATION
    assert admission.status == AdmissionStatus.PENDING_BED
    assert admission.authorization_status == AuthorizationStatus.AUTHORIZED
    assert admission.authorization_number == "AUT-9001"
    assert authorization.status == AuthorizationState.AUTHORIZED
    assert authorization.authorized_at is not None
    assert HospitalizationEventType.ADMISSION_AUTHORIZED in events


def test_rejected_authorization_rejects_the_admission_request():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission_id = (
                await AdmissionWorkflowService(session).create(admission_payload(scenario))
            ).id
        async with factory() as session:
            authorization_id = (
                await AuthorizationService(session).request_for_admission(
                    admission_id,
                    AuthorizationRequestCreate(),
                )
            ).id
        async with factory() as session:
            await AuthorizationService(session).resolve(
                authorization_id,
                AuthorizationResolveCreate(status=AuthorizationState.REJECTED),
            )
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            return admission.status, admission.authorization_status

    status, authorization_status = run_db(case)

    assert status == AdmissionStatus.REJECTED
    assert authorization_status == AuthorizationStatus.REJECTED


def test_discharge_planning_keeps_the_hospitalization_and_the_bed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            plan = await HospitalizationService(session).plan_discharge(
                hospitalization_id,
                DischargePlanCreate(created_by="medico"),
            )
            plan_id = plan.id
        async with factory() as check:
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            bed = await check.get(Bed, scenario.bed_ids[0])
            plans = await HospitalizationService(check).discharge_plans(hospitalization_id)
            return hospitalization.status, bed.status, plans, plan_id

    status, bed_status, plans, plan_id = run_db(case)

    assert status == HospitalizationStatus.DISCHARGE_PLANNED
    assert bed_status == BedStatus.OCCUPIED
    assert [plan.id for plan in plans] == [plan_id]
    assert plans[0].status == DischargePlanStatus.PLANNED


def test_clinical_discharge_does_not_release_the_bed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(discharge_reason="Evolución favorable"),
            )
        async with factory() as check:
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            bed = await check.get(Bed, scenario.bed_ids[0])
            assignment = await check.scalar(
                select(BedAssignment).where(
                    BedAssignment.hospitalization_id == hospitalization_id,
                    BedAssignment.ended_at.is_(None),
                )
            )
            account = await AccountService(check).for_hospitalization(hospitalization_id)
            return hospitalization, bed.status, assignment, account.status

    hospitalization, bed_status, assignment, account_status = run_db(case)

    assert hospitalization.status == HospitalizationStatus.CLINICALLY_DISCHARGED
    assert hospitalization.clinically_discharged_at is not None
    assert hospitalization.physically_departed_at is None
    assert bed_status == BedStatus.OCCUPIED
    assert assignment is not None
    # Clinical discharge does not depend on the financial closure.
    assert account_status == AccountStatus.OPEN


def test_physical_departure_requires_the_clinical_discharge():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).physical_departure(
                    hospitalization_id,
                    PhysicalDepartureCreate(),
                )
            return error.value.status_code

    assert run_db(case) == 409


def test_physical_departure_releases_the_bed_to_cleaning():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as session:
            await HospitalizationService(session).physical_departure(
                hospitalization_id,
                PhysicalDepartureCreate(released_by="enfermeria"),
            )
        async with factory() as check:
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            bed = await check.get(Bed, scenario.bed_ids[0])
            active = await check.scalar(
                select(BedAssignment.id).where(
                    BedAssignment.hospitalization_id == hospitalization_id,
                    BedAssignment.ended_at.is_(None),
                )
            )
            return hospitalization, bed.status, active

    hospitalization, bed_status, active = run_db(case)

    assert hospitalization.status == HospitalizationStatus.CLINICALLY_DISCHARGED
    assert hospitalization.physically_departed_at is not None
    assert hospitalization.clinically_discharged_at <= hospitalization.physically_departed_at
    assert bed_status == BedStatus.PENDING_CLEANING
    assert active is None


def test_administrative_discharge_requires_the_physical_departure():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).administrative_discharge(
                    hospitalization_id,
                    AdministrativeDischargeCreate(),
                )
            return error.value.status_code

    assert run_db(case) == 409


def test_administrative_discharge_closes_history_and_hands_over_the_account():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission_id = (
                await AdmissionWorkflowService(session).create(
                    admission_payload(
                        scenario,
                        requested_bed_id=scenario.bed_ids[0],
                        confirm_admission=True,
                    )
                )
            ).id
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            hospitalization_id = admission.hospitalization_id
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as session:
            await HospitalizationService(session).physical_departure(
                hospitalization_id,
                PhysicalDepartureCreate(),
            )
        async with factory() as session:
            await HospitalizationService(session).administrative_discharge(
                hospitalization_id,
                AdministrativeDischargeCreate(notes="Documentación completa"),
            )
        async with factory() as check:
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            admission = await check.get(Admission, admission_id)
            episode = await check.get(Episode, admission.episode_id)
            account = await AccountService(check).for_hospitalization(hospitalization_id)
            services = await HospitalizationService(check).list_service_assignments(
                hospitalization_id
            )
            care_team = await HospitalizationService(check).care_team(hospitalization_id)
            return hospitalization, admission, episode, account, services, care_team

    hospitalization, admission, episode, account, services, care_team = run_db(case)

    assert hospitalization.status == HospitalizationStatus.ADMINISTRATIVELY_DISCHARGED
    assert hospitalization.administratively_discharged_at is not None
    assert hospitalization.closed_at is None
    assert admission.status == AdmissionStatus.ADMINISTRATIVE_DISCHARGE
    assert episode.status == EpisodeStatus.CLOSED
    assert account.status == AccountStatus.READY_FOR_REVIEW
    assert all(assignment.ended_at is not None for assignment in services)
    assert all(member.ended_at is not None for member in care_team.members)


def test_account_closure_closes_the_hospitalization():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            await AccountService(session).add_charge_item(
                hospitalization_id,
                ChargeItemCreate(
                    category="HOSPITALIZATION_DAY",
                    description="Día de internación",
                    quantity=2,
                    unit_price="1500.00",
                ),
            )
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as session:
            await HospitalizationService(session).physical_departure(
                hospitalization_id,
                PhysicalDepartureCreate(),
            )
        async with factory() as session:
            await HospitalizationService(session).administrative_discharge(
                hospitalization_id,
                AdministrativeDischargeCreate(),
            )
        async with factory() as check:
            account = await AccountService(check).for_hospitalization(hospitalization_id)
            account_id, total = account.id, AccountService.total(account)
        async with factory() as session:
            await AccountService(session).close(account_id, actor="facturacion")
        async with factory() as check:
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            account = await check.get(Account, account_id)
            return hospitalization, account, total

    hospitalization, account, total = run_db(case)

    assert str(total) == "3000.00"
    assert account.status == AccountStatus.CLOSED
    assert hospitalization.status == HospitalizationStatus.CLOSED
    assert hospitalization.closed_at is not None


def test_service_reassignment_keeps_the_previous_assignment_as_history():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            await HospitalizationService(session).assign_service(
                hospitalization_id,
                ServiceAssignmentCreate(
                    service_id=scenario.other_service_id,
                    reason="Pase a terapia intensiva",
                ),
            )
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).assign_service(
                    hospitalization_id,
                    ServiceAssignmentCreate(service_id=scenario.other_service_id),
                )
            repeated = error.value.status_code
        async with factory() as check:
            services = await HospitalizationService(check).list_service_assignments(
                hospitalization_id
            )
            return services, repeated

    services, repeated = run_db(case)

    assert repeated == 409
    assert len(services) == 2
    assert services[0].ended_at is None
    assert services[1].ended_at is not None


def test_care_team_membership_is_closed_instead_of_deleted():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await admitted_hospitalization(factory, scenario)
        async with factory() as session:
            member = await HospitalizationService(session).add_care_team_member(
                hospitalization_id,
                CareTeamMemberCreate(
                    practitioner_id=scenario.practitioner_id,
                    role=CareTeamRole.NURSE,
                ),
            )
            member_id = member.id
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).add_care_team_member(
                    hospitalization_id,
                    CareTeamMemberCreate(
                        practitioner_id=scenario.practitioner_id,
                        role=CareTeamRole.NURSE,
                    ),
                )
            duplicated = error.value.status_code
        async with factory() as session:
            await HospitalizationService(session).end_care_team_member(
                hospitalization_id,
                member_id,
            )
        async with factory() as check:
            care_team = await HospitalizationService(check).care_team(hospitalization_id)
            return duplicated, care_team.members, member_id

    duplicated, members, member_id = run_db(case)

    assert duplicated == 409
    # The attending physician of the admission request plus the nurse that was added.
    assert {member.role for member in members} == {
        CareTeamRole.ATTENDING_PHYSICIAN,
        CareTeamRole.NURSE,
    }
    nurse = next(member for member in members if member.id == member_id)
    attending = next(member for member in members if member.id != member_id)
    assert nurse.ended_at is not None
    assert attending.ended_at is None


async def registered_request(session, scenario, **overrides) -> Admission:
    """Admission request stored without a hospitalization yet."""

    payload = admission_payload(scenario, **overrides)
    admission = Admission(
        patient_id=payload.patient_id,
        facility_id=payload.facility_id,
        requesting_service_id=payload.requesting_service_id,
        origin=payload.origin,
        admission_type=payload.admission_type,
        status=AdmissionStatus.PRE_ADMITTED,
        identity_validated=payload.identity_validated,
        duplicate_checked=payload.duplicate_checked,
        authorization_status=payload.authorization_status,
        responsible_contact_name=payload.responsible_contact_name,
        responsible_contact_phone=payload.responsible_contact_phone,
        admission_reason=payload.admission_reason,
        responsible_physician=payload.responsible_physician,
        responsible_physician_id=payload.responsible_physician_id,
        requested_at=datetime.now(UTC),
    )
    session.add(admission)
    await session.commit()
    return admission


def test_hospitalization_is_created_from_a_registered_admission_request():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            admission = await registered_request(setup, scenario)
            admission_id = admission.id
        async with factory() as session:
            hospitalization = await HospitalizationService(session).create_from_admission(
                HospitalizationCreate(admission_id=admission_id),
            )
            hospitalization_id = hospitalization.id
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            services = await HospitalizationService(check).list_service_assignments(
                hospitalization_id
            )
            return admission, hospitalization, services

    admission, hospitalization, services = run_db(case)

    assert admission.hospitalization_id == hospitalization.id
    assert admission.status == AdmissionStatus.PENDING_BED
    assert admission.episode_id == hospitalization.episode_id
    assert hospitalization.status == HospitalizationStatus.PENDING_BED
    assert hospitalization.admission_type == admission.admission_type
    assert hospitalization.facility_id == admission.facility_id
    assert [item.service_id for item in services] == [admission.requesting_service_id]


def test_hospitalization_requires_an_existing_admission_request():
    async def case(factory):
        async with factory() as setup:
            await build_scenario(setup)
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).create_from_admission(
                    HospitalizationCreate(admission_id=uuid.uuid4()),
                )
            return error.value.status_code

    assert run_db(case) == 404


def test_admission_request_cannot_produce_two_hospitalizations():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission = await AdmissionWorkflowService(session).create(
                admission_payload(scenario)
            )
            admission_id = admission.id
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).create_from_admission(
                    HospitalizationCreate(admission_id=admission_id),
                )
            return error.value.status_code

    assert run_db(case) == 409


def test_pending_authorization_blocks_the_hospitalization():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
            admission = await registered_request(
                setup,
                scenario,
                authorization_status=AuthorizationStatus.PENDING,
            )
            admission_id = admission.id
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).create_from_admission(
                    HospitalizationCreate(admission_id=admission_id),
                )
            return error.value.status_code

    assert run_db(case) == 409


def test_rejected_authorization_cancels_the_pending_hospitalization():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission = await AdmissionWorkflowService(session).create(
                admission_payload(scenario, authorization_status=AuthorizationStatus.NOT_REQUIRED)
            )
            admission_id, hospitalization_id = admission.id, admission.hospitalization_id
        async with factory() as session:
            authorization_id = (
                await AuthorizationService(session).request_for_admission(
                    admission_id,
                    AuthorizationRequestCreate(),
                )
            ).id
        async with factory() as session:
            await AuthorizationService(session).resolve(
                authorization_id,
                AuthorizationResolveCreate(status=AuthorizationState.REJECTED),
            )
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            events = list(
                (
                    await check.scalars(
                        select(HospitalizationEvent.event_type).where(
                            HospitalizationEvent.hospitalization_id == hospitalization_id
                        )
                    )
                ).all()
            )
            return admission, hospitalization, events

    admission, hospitalization, events = run_db(case)

    assert admission.status == AdmissionStatus.REJECTED
    assert hospitalization.status == HospitalizationStatus.CANCELLED
    assert HospitalizationEventType.HOSPITALIZATION_CANCELLED in events
