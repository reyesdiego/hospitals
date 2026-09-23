"""Una orden médica programada no admite nada clínico hasta que el paciente llega."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import DomainError
from app.core.users import RequestUser
from app.models.account import Account, AccountStatus
from app.models.admission import (
    Admission,
    AdmissionOrigin,
    AdmissionStatus,
    AdmissionType,
    Episode,
    EpisodeStatus,
)
from app.models.bed import Bed, BedReservation, BedReservationStatus, BedStatus
from app.models.care_team import CareTeamRole
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.prescription import PrescriptionKind
from app.models.treatment import MedicationRoute
from app.schemas.domain import AdmissionArrivalCreate, AdmissionCancelCreate
from app.schemas.practice import HospitalizationPracticeCreate
from app.schemas.prescription import DischargePrescriptionCreate
from app.schemas.treatment import TreatmentCreate
from app.schemas.workflow import CareTeamMemberCreate, ChargeItemCreate, ServiceAssignmentCreate
from app.services.account import AccountService
from app.services.admission import AdmissionWorkflowService
from app.services.bed_assignment import BedAssignmentService
from app.services.hospitalization import HospitalizationService
from app.services.practice import HospitalizationPracticeService
from app.services.prescription import DischargePrescriptionService
from app.services.treatment import HospitalizationTreatmentService
from tests.conftest import requires_postgres, run_db
from tests.factories import admission_payload, build_scenario, hospitalization_from_admission
from tests.test_post_discharge_lock_pg import PERFORMED_AT, catalog_practice

pytestmark = requires_postgres

ADMIN = RequestUser(role="admin", name="Ana Supervisora")
DOCTOR = RequestUser(role="DOCTOR", name="Dra. Lopez")


async def scheduled_order(factory, scenario):
    """Orden médica programada con la cama reservada: el paciente todavía no llegó."""

    async with factory() as session:
        return await hospitalization_from_admission(
            session,
            scenario,
            origin=AdmissionOrigin.SCHEDULED_MEDICAL_ORDER,
            admission_type=AdmissionType.SCHEDULED,
            responsible_contact_name=None,
            responsible_contact_phone=None,
            requested_bed_id=scenario.bed_ids[0],
        )


def practice_payload(scenario, practice):
    return HospitalizationPracticeCreate(
        practice_id=practice.id,
        prescribed_by_id=scenario.practitioner_id,
        performed_at=PERFORMED_AT,
    )


def test_nothing_clinical_can_be_done_before_the_patient_arrives():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await scheduled_order(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)

        attempts = {
            # Ni siquiera un administrador: no hay a quién hacerle la práctica.
            "practice": lambda session: HospitalizationPracticeService(session, ADMIN).register(
                hospitalization_id, practice_payload(scenario, practice)
            ),
            "treatment": lambda session: HospitalizationTreatmentService(session, DOCTOR).add(
                hospitalization_id,
                TreatmentCreate(
                    description="Amoxicilina",
                    presentation="500 mg",
                    dose="1 comprimido",
                    route=MedicationRoute.ORAL,
                    frequency="cada 8 horas",
                    prescribed_by_id=scenario.practitioner_id,
                ),
            ),
            "prescription": lambda session: DischargePrescriptionService(session, DOCTOR).add(
                hospitalization_id,
                DischargePrescriptionCreate(
                    kind=PrescriptionKind.MEDICATION,
                    description="Amoxicilina",
                    presentation="comprimidos 500 mg",
                    dosage="1 cada 8 horas",
                    quantity=Decimal(2),
                    duration_days=7,
                    prescribed_by_id=scenario.practitioner_id,
                ),
            ),
            "charge": lambda session: AccountService(session).add_charge_item(
                hospitalization_id,
                ChargeItemCreate(
                    category="MEDICATION",
                    description="Analgésico",
                    quantity=Decimal(1),
                    unit_price=Decimal("1500.00"),
                ),
            ),
            # Tampoco se reorganiza quién lo atiende: hasta que llega solo hay una cama.
            "service": lambda session: HospitalizationService(session).assign_service(
                hospitalization_id, ServiceAssignmentCreate(service_id=scenario.other_service_id)
            ),
            "care_team": lambda session: HospitalizationService(session).add_care_team_member(
                hospitalization_id,
                CareTeamMemberCreate(
                    practitioner_id=scenario.practitioner_id, role=CareTeamRole.SPECIALIST
                ),
            ),
        }
        outcomes = {}
        for name, attempt in attempts.items():
            async with factory() as session:
                with pytest.raises(DomainError) as error:
                    await attempt(session)
                outcomes[name] = (error.value.status_code, "todavía no ingresó" in error.value.message)
        async with factory() as check:
            status = (await check.get(Hospitalization, hospitalization_id)).status
        return status, outcomes

    status, outcomes = run_db(case)

    assert status == HospitalizationStatus.AWAITING_ARRIVAL
    assert outcomes == {
        "practice": (409, True),
        "treatment": (409, True),
        "prescription": (409, True),
        "charge": (409, True),
        "service": (409, True),
        "care_team": (409, True),
    }


def test_once_admitted_on_the_reserved_bed_the_stay_accepts_practices():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await scheduled_order(factory, scenario)
        async with factory() as session:
            practice = await catalog_practice(session)
        async with factory() as session:
            await BedAssignmentService(session).assign(
                hospitalization_id,
                scenario.bed_ids[0],
                arrival=AdmissionArrivalCreate(
                    responsible_contact_name="Ana Perez",
                    responsible_contact_phone="11-4444-4444",
                ),
            )
        async with factory() as session:
            order = await HospitalizationPracticeService(session, DOCTOR).register(
                hospitalization_id, practice_payload(scenario, practice)
            )
            order_status = order.status.value
        async with factory() as check:
            status = (await check.get(Hospitalization, hospitalization_id)).status
        return status, order_status

    assert run_db(case) == (HospitalizationStatus.IN_PROGRESS, "PERFORMED")


def test_cancelling_the_order_frees_the_bed_and_closes_everything_it_opened():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await scheduled_order(factory, scenario)
        async with factory() as check:
            admission = await check.scalar(
                select(Admission).where(Admission.hospitalization_id == hospitalization_id)
            )
            admission_id = admission.id
        async with factory() as session:
            await AdmissionWorkflowService(session).cancel(
                admission_id, AdmissionCancelCreate(reason="El paciente no se presento")
            )
        async with factory() as check:
            admission = await check.get(Admission, admission_id)
            hospitalization = await check.get(Hospitalization, hospitalization_id)
            episode = await check.get(Episode, admission.episode_id)
            account = await check.scalar(
                select(Account).where(Account.hospitalization_id == hospitalization_id)
            )
            reservation = await check.scalar(
                select(BedReservation).where(
                    BedReservation.hospitalization_id == hospitalization_id
                )
            )
            bed = await check.get(Bed, scenario.bed_ids[0])
            result = (
                admission.status,
                hospitalization.status,
                episode.status,
                account.status,
                reservation.status,
                bed.status,
            )
        # Cancelada la orden, el paciente puede volver a admitirse.
        async with factory() as session:
            again = await AdmissionWorkflowService(session).create(admission_payload(scenario))
            return result, again.status

    result, again = run_db(case)

    assert result == (
        AdmissionStatus.CANCELLED,
        HospitalizationStatus.CANCELLED,
        EpisodeStatus.CANCELLED,
        AccountStatus.CANCELLED,
        BedReservationStatus.CANCELLED,
        BedStatus.AVAILABLE,
    )
    assert again == AdmissionStatus.PENDING_BED


def test_an_order_whose_patient_already_arrived_cannot_be_cancelled():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            admission = await AdmissionWorkflowService(session).create(
                admission_payload(scenario, requested_bed_id=scenario.bed_ids[0], confirm_admission=True)
            )
            admission_id = admission.id
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await AdmissionWorkflowService(session).cancel(
                    admission_id, AdmissionCancelCreate(reason="Error de carga")
                )
            return error.value.status_code

    assert run_db(case) == 409
