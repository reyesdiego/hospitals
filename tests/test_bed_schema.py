from app.models.bed import Bed, BedAssignment, BedTransfer


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


def test_active_assignment_unique_indexes_exist():
    indexes = {index.name: index for index in BedAssignment.__table__.indexes}

    assert "uq_active_assignment_per_bed" in indexes
    assert "uq_active_bed_per_hospitalization" in indexes
    assert indexes["uq_active_assignment_per_bed"].unique is True
    assert indexes["uq_active_bed_per_hospitalization"].unique is True
    assert indexes["uq_active_assignment_per_bed"].dialect_options["postgresql"]["where"] is not None
    assert indexes["uq_active_bed_per_hospitalization"].dialect_options["postgresql"]["where"] is not None


def test_bed_transfer_audit_table_references_hospitalization_and_beds():
    columns = BedTransfer.__table__.c

    assert columns.hospitalization_id.nullable is False
    assert columns.from_bed_id.nullable is False
    assert columns.to_bed_id.nullable is False
    assert columns.requested_at.nullable is False
    assert columns.status.nullable is False
