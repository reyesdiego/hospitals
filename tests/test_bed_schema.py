from app.models.bed import (
    Bed,
    BedAssignment,
    BedReservation,
    BedStatus,
    BedStatusHistory,
    BedTransfer,
)
from app.models.care_team import CareTeamMember
from app.models.discharge import DischargePlan
from app.models.hospitalization import Hospitalization, HospitalizationServiceAssignment


def indexes(model):
    return {index.name: index for index in model.__table__.indexes}


def test_bed_belongs_to_exactly_one_room_in_schema():
    room_id = Bed.__table__.c.room_id

    assert room_id.nullable is False
    assert len(room_id.foreign_keys) == 1

    foreign_key = next(iter(room_id.foreign_keys))
    assert foreign_key.column.table.name == "rooms"
    assert foreign_key.column.name == "id"
    assert foreign_key.ondelete == "RESTRICT"


def test_bed_has_operational_status_column():
    status = Bed.__table__.c.status

    assert status.nullable is False
    assert status.default is not None
    assert str(status.server_default.arg) == "AVAILABLE"


def test_bed_status_supports_the_whole_turnaround_cycle():
    assert {status.value for status in BedStatus} >= {
        "AVAILABLE",
        "RESERVED",
        "OCCUPIED",
        "PENDING_CLEANING",
        "CLEANING",
        "BLOCKED",
        "MAINTENANCE",
        "OUT_OF_SERVICE",
    }


def test_bed_assignment_is_only_physical_occupancy():
    columns = BedAssignment.__table__.c

    assert "status" not in columns
    assert columns.hospitalization_id.nullable is False


def test_active_assignment_unique_indexes_exist():
    assignment_indexes = indexes(BedAssignment)

    assert assignment_indexes["uq_active_assignment_per_bed"].unique is True
    assert assignment_indexes["uq_active_bed_per_hospitalization"].unique is True
    assert (
        assignment_indexes["uq_active_assignment_per_bed"].dialect_options["postgresql"]["where"]
        is not None
    )
    assert (
        assignment_indexes["uq_active_bed_per_hospitalization"]
        .dialect_options["postgresql"]["where"]
        is not None
    )


def test_single_active_reservation_per_bed_and_hospitalization():
    reservation_indexes = indexes(BedReservation)

    for name in ("uq_active_reservation_per_bed", "uq_active_reservation_per_hospitalization"):
        assert reservation_indexes[name].unique is True
        assert reservation_indexes[name].dialect_options["postgresql"]["where"] is not None


def test_bed_status_history_is_append_only_with_both_statuses():
    columns = BedStatusHistory.__table__.c

    assert columns.previous_status.nullable is True
    assert columns.new_status.nullable is False
    assert columns.changed_at.nullable is False


def test_bed_transfer_audit_table_references_hospitalization_and_beds():
    columns = BedTransfer.__table__.c

    assert columns.hospitalization_id.nullable is False
    assert columns.from_bed_id.nullable is False
    assert columns.to_bed_id.nullable is False
    assert columns.requested_at.nullable is False
    assert columns.status.nullable is False


def test_hospitalization_keeps_each_lifecycle_moment_in_its_own_column():
    columns = Hospitalization.__table__.c

    assert "discharged_at" not in columns
    for name in (
        "admitted_at",
        "clinically_discharged_at",
        "physically_departed_at",
        "administratively_discharged_at",
        "closed_at",
    ):
        assert columns[name].nullable is True
    assert "episode_id" in columns
    assert "facility_id" in columns


def test_single_active_service_assignment_per_hospitalization():
    service_indexes = indexes(HospitalizationServiceAssignment)

    assert service_indexes["uq_active_service_per_hospitalization"].unique is True


def test_single_active_attending_physician_per_care_team():
    member_indexes = indexes(CareTeamMember)

    assert member_indexes["uq_active_attending_physician"].unique is True
    assert member_indexes["uq_active_care_team_member_role"].unique is True


def test_single_active_discharge_plan_per_hospitalization():
    plan_indexes = indexes(DischargePlan)

    assert plan_indexes["uq_active_discharge_plan_per_hospitalization"].unique is True
