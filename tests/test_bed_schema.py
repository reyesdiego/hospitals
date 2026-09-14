from app.models.bed import Bed


def test_bed_belongs_to_exactly_one_room_in_schema():
    room_id = Bed.__table__.c.room_id

    assert room_id.nullable is False
    assert len(room_id.foreign_keys) == 1

    foreign_key = next(iter(room_id.foreign_keys))
    assert foreign_key.column.table.name == "rooms"
    assert foreign_key.column.name == "id"
    assert foreign_key.ondelete == "RESTRICT"
