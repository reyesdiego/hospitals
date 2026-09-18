"""Bed lifecycle against PostgreSQL: reservation, occupancy, transfer and cleaning."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DomainError
from app.models.bed import (
    Bed,
    BedAssignment,
    BedReservation,
    BedReservationStatus,
    BedStatus,
    BedStatusHistory,
)
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.services.bed_assignment import BedAssignmentService
from app.services.bed_reservation import BedReservationService
from app.services.bed_status import BedStatusService
from app.services.hospitalization import HospitalizationService
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, request_admission

pytestmark = requires_postgres


async def _hospitalization(session, scenario, **overrides) -> Hospitalization:
    """Stay created through its admission request, as the API requires."""

    admission = await request_admission(session, scenario, **overrides)
    # Read inside its own transaction so the session is left clean for the service calls.
    async with session.begin():
        return await HospitalizationService(session).get(admission.hospitalization_id)


def test_reservation_holds_the_bed_and_assignment_confirms_the_admission():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization = await _hospitalization(session, scenario)
            reservation = await BedReservationService(session).reserve(
                hospitalization.id,
                scenario.bed_ids[0],
                reserved_by="admision",
            )
            assignment = await BedAssignmentService(session).assign(
                hospitalization.id,
                scenario.bed_ids[0],
                assigned_by="enfermeria",
            )
        async with factory() as check:
            bed = await check.get(Bed, scenario.bed_ids[0])
            stored_reservation = await check.get(BedReservation, reservation.id)
            stored_hospitalization = await check.get(Hospitalization, hospitalization.id)
            history = list(
                (
                    await check.scalars(
                        select(BedStatusHistory)
                        .where(BedStatusHistory.bed_id == scenario.bed_ids[0])
                        .order_by(BedStatusHistory.changed_at)
                    )
                ).all()
            )
            return bed.status, stored_reservation.status, stored_hospitalization, assignment, history

    status, reservation_status, hospitalization, assignment, history = run_db(case)

    assert status == BedStatus.OCCUPIED
    assert reservation_status == BedReservationStatus.COMPLETED
    assert hospitalization.status == HospitalizationStatus.IN_PROGRESS
    assert hospitalization.admitted_at is not None
    assert assignment.ended_at is None
    assert [entry.new_status for entry in history] == [BedStatus.RESERVED, BedStatus.OCCUPIED]


def test_cannot_reserve_a_bed_that_is_already_occupied():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            first = await _hospitalization(session, scenario)
            await BedAssignmentService(session).assign(first.id, scenario.bed_ids[0])
            second = await _hospitalization(session, scenario, patient_id=scenario.other_patient_id)
            with pytest.raises(DomainError) as error:
                await BedReservationService(session).reserve(second.id, scenario.bed_ids[0])
            return error.value.status_code

    assert run_db(case) == 409


def test_expired_reservation_releases_the_bed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization = await _hospitalization(session, scenario)
            reservation = await BedReservationService(session).reserve(
                hospitalization.id,
                scenario.bed_ids[0],
                expires_in_minutes=1,
            )
        async with factory() as ageing, ageing.begin():
            stored = await ageing.get(BedReservation, reservation.id)
            stored.reserved_at = stored.reserved_at - timedelta(hours=2)
            stored.expires_at = stored.expires_at - timedelta(hours=2)
        async with factory() as session:
            expired = await BedReservationService(session).expire_due()
        async with factory() as check:
            bed = await check.get(Bed, scenario.bed_ids[0])
            stored = await check.get(BedReservation, reservation.id)
            return len(expired), stored.status, bed.status

    count, status, bed_status = run_db(case)

    assert count == 1
    assert status == BedReservationStatus.EXPIRED
    assert bed_status == BedStatus.AVAILABLE


def test_database_rejects_two_active_assignments_on_the_same_bed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            first = await _hospitalization(session, scenario)
            second = await _hospitalization(session, scenario, patient_id=scenario.other_patient_id)
            first_id, second_id = first.id, second.id
            await BedAssignmentService(session).assign(first_id, scenario.bed_ids[0])
        async with factory() as raw:
            raw.add(
                BedAssignment(
                    hospitalization_id=second_id,
                    bed_id=scenario.bed_ids[0],
                    started_at=datetime.now(UTC),
                )
            )
            with pytest.raises(IntegrityError):
                await raw.commit()
            await raw.rollback()
        return True

    assert run_db(case) is True


def test_database_rejects_two_active_beds_for_the_same_hospitalization():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization_id = (await _hospitalization(session, scenario)).id
            await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
        async with factory() as raw:
            raw.add(
                BedAssignment(
                    hospitalization_id=hospitalization_id,
                    bed_id=scenario.bed_ids[1],
                    started_at=datetime.now(UTC),
                )
            )
            with pytest.raises(IntegrityError):
                await raw.commit()
            await raw.rollback()
        return True

    assert run_db(case) is True


def test_concurrent_reservations_on_the_same_bed_allow_only_one():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            first = await _hospitalization(session, scenario)
            second = await _hospitalization(session, scenario, patient_id=scenario.other_patient_id)

        async def reserve(hospitalization_id):
            async with factory() as session:
                return await BedReservationService(session).reserve(
                    hospitalization_id,
                    scenario.bed_ids[0],
                )

        results = await asyncio.gather(
            reserve(first.id),
            reserve(second.id),
            return_exceptions=True,
        )
        async with factory() as check:
            active = list(
                (
                    await check.scalars(
                        select(BedReservation).where(
                            BedReservation.bed_id == scenario.bed_ids[0],
                            BedReservation.status == BedReservationStatus.ACTIVE,
                        )
                    )
                ).all()
            )
            return results, len(active)

    results, active = run_db(case)

    successes = [item for item in results if isinstance(item, BedReservation)]
    failures = [item for item in results if isinstance(item, DomainError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 409
    assert active == 1


def test_concurrent_assignments_on_the_same_bed_allow_only_one():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            first = await _hospitalization(session, scenario)
            second = await _hospitalization(session, scenario, patient_id=scenario.other_patient_id)

        async def assign(hospitalization_id):
            async with factory() as session:
                return await BedAssignmentService(session).assign(
                    hospitalization_id,
                    scenario.bed_ids[0],
                )

        results = await asyncio.gather(
            assign(first.id),
            assign(second.id),
            return_exceptions=True,
        )
        async with factory() as check:
            active = list(
                (
                    await check.scalars(
                        select(BedAssignment).where(
                            BedAssignment.bed_id == scenario.bed_ids[0],
                            BedAssignment.ended_at.is_(None),
                        )
                    )
                ).all()
            )
            return results, len(active)

    results, active = run_db(case)

    successes = [item for item in results if isinstance(item, BedAssignment)]
    failures = [item for item in results if isinstance(item, DomainError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert active == 1


def test_transfer_moves_the_patient_and_keeps_both_assignments():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization = await _hospitalization(session, scenario)
            await BedAssignmentService(session).assign(hospitalization.id, scenario.bed_ids[0])
            transfer = await BedAssignmentService(session).transfer(
                hospitalization.id,
                scenario.bed_ids[1],
                reason="Pase a terapia intensiva",
                completed_by="enfermeria",
                service_id=scenario.other_service_id,
            )
        async with factory() as check:
            source = await check.get(Bed, scenario.bed_ids[0])
            destination = await check.get(Bed, scenario.bed_ids[1])
            assignments = list(
                (
                    await check.scalars(
                        select(BedAssignment)
                        .where(BedAssignment.hospitalization_id == hospitalization.id)
                        .order_by(BedAssignment.started_at)
                    )
                ).all()
            )
            services = await HospitalizationService(check).list_service_assignments(
                hospitalization.id
            )
            return transfer, source.status, destination.status, assignments, services

    transfer, source_status, destination_status, assignments, services = run_db(case)

    assert transfer.from_bed_id != transfer.to_bed_id
    assert source_status == BedStatus.PENDING_CLEANING
    assert destination_status == BedStatus.OCCUPIED
    assert len(assignments) == 2
    assert assignments[0].ended_at is not None
    assert assignments[1].ended_at is None
    assert len(services) == 2
    assert services[0].ended_at is None
    assert services[1].ended_at is not None


def test_failed_transfer_keeps_the_patient_in_the_original_bed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            first_id = (await _hospitalization(session, scenario)).id
            second_id = (await _hospitalization(session, scenario, patient_id=scenario.other_patient_id)).id
            await BedAssignmentService(session).assign(first_id, scenario.bed_ids[0])
            await BedAssignmentService(session).assign(second_id, scenario.bed_ids[1])
            with pytest.raises(DomainError) as error:
                await BedAssignmentService(session).transfer(first_id, scenario.bed_ids[1])
            status_code = error.value.status_code
        async with factory() as check:
            source = await check.get(Bed, scenario.bed_ids[0])
            assignment = await check.scalar(
                select(BedAssignment).where(
                    BedAssignment.hospitalization_id == first_id,
                    BedAssignment.ended_at.is_(None),
                )
            )
            return status_code, source.status, assignment.bed_id

    status_code, source_status, bed_id = run_db(case)

    assert status_code == 409
    assert source_status == BedStatus.OCCUPIED
    assert bed_id is not None


def test_transfer_to_the_same_bed_is_rejected():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization = await _hospitalization(session, scenario)
            await BedAssignmentService(session).assign(hospitalization.id, scenario.bed_ids[0])
            with pytest.raises(DomainError) as error:
                await BedAssignmentService(session).transfer(
                    hospitalization.id,
                    scenario.bed_ids[0],
                )
            return error.value.status_code

    assert run_db(case) == 409


def test_cleaning_cycle_returns_the_bed_to_available():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization = await _hospitalization(session, scenario)
            await BedAssignmentService(session).assign(hospitalization.id, scenario.bed_ids[0])
            await HospitalizationService(session).release_bed(hospitalization.id)
        statuses = []
        async with factory() as session:
            released = await session.get(Bed, scenario.bed_ids[0])
            statuses.append(released.status)
        async with factory() as session:
            bed = await BedStatusService(session).start_cleaning(
                scenario.bed_ids[0],
                changed_by="limpieza",
            )
            statuses.append(bed.status)
        async with factory() as session:
            bed = await BedStatusService(session).complete_cleaning(
                scenario.bed_ids[0],
                changed_by="limpieza",
            )
            statuses.append(bed.status)
        async with factory() as check:
            history = list(
                (
                    await check.scalars(
                        select(BedStatusHistory)
                        .where(BedStatusHistory.bed_id == scenario.bed_ids[0])
                        .order_by(BedStatusHistory.changed_at)
                    )
                ).all()
            )
            available = await BedStatusService(check).search_available(
                facility_id=scenario.facility_id
            )
            return statuses, [entry.new_status for entry in history], len(available)

    statuses, history, available = run_db(case)

    assert statuses == [BedStatus.PENDING_CLEANING, BedStatus.CLEANING, BedStatus.AVAILABLE]
    assert history == [
        BedStatus.OCCUPIED,
        BedStatus.PENDING_CLEANING,
        BedStatus.CLEANING,
        BedStatus.AVAILABLE,
    ]
    assert available == 2


def test_operational_status_is_rejected_while_the_bed_is_occupied():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization = await _hospitalization(session, scenario)
            await BedAssignmentService(session).assign(hospitalization.id, scenario.bed_ids[0])
            with pytest.raises(DomainError) as error:
                await BedStatusService(session).set_status(
                    scenario.bed_ids[0],
                    BedStatus.MAINTENANCE,
                )
            return error.value.status_code

    assert run_db(case) == 409


def test_reserving_a_bed_with_an_expired_hold_takes_over_the_bed():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            first = await _hospitalization(session, scenario)
            second = await _hospitalization(session, scenario, patient_id=scenario.other_patient_id)
            first_id, second_id = first.id, second.id
            stale = await BedReservationService(session).reserve(first_id, scenario.bed_ids[0])
        async with factory() as ageing, ageing.begin():
            reservation = await ageing.get(BedReservation, stale.id)
            reservation.reserved_at = reservation.reserved_at - timedelta(hours=4)
            reservation.expires_at = reservation.expires_at - timedelta(hours=4)
        async with factory() as session:
            taken = await BedReservationService(session).reserve(second_id, scenario.bed_ids[0])
        async with factory() as check:
            previous = await check.get(BedReservation, stale.id)
            bed = await check.get(Bed, scenario.bed_ids[0])
            return previous.status, taken.hospitalization_id, second_id, bed.status

    previous_status, holder, expected_holder, bed_status = run_db(case)

    assert previous_status == BedReservationStatus.EXPIRED
    assert holder == expected_holder
    assert bed_status == BedStatus.RESERVED


def test_beds_board_shows_the_occupant_and_the_reservation_holder():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            occupied = await _hospitalization(session, scenario)
            reserved = await _hospitalization(session, scenario, patient_id=scenario.other_patient_id)
            await BedAssignmentService(session).assign(occupied.id, scenario.bed_ids[0])
            await BedReservationService(session).reserve(reserved.id, scenario.bed_ids[1])
        async with factory() as check:
            rows = await BedStatusService(check).board()
            return {
                bed.id: (bed.status, occupant, holder, expires_at)
                for bed, _room, occupant, holder, expires_at in rows
            }, scenario

    board, scenario = run_db(case)

    occupied_status, occupant, occupied_holder, _ = board[scenario.bed_ids[0]]
    reserved_status, reserved_occupant, holder, expires_at = board[scenario.bed_ids[1]]
    assert occupied_status == BedStatus.OCCUPIED
    assert occupant is not None and occupant.id == scenario.patient_id
    assert occupied_holder is None
    assert reserved_status == BedStatus.RESERVED
    assert reserved_occupant is None
    assert holder is not None and holder.id == scenario.other_patient_id
    assert expires_at is not None
