"""El estado de una habitación sale de sus camas."""

from app.models.bed import Bed, BedStatus
from app.models.room import Room, RoomStatus
from app.services.room import occupancy_by_room, occupancy_of
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario


def room(status: RoomStatus = RoomStatus.AVAILABLE) -> Room:
    return Room(code="101", ward="Clínica Médica", status=status)


def test_a_room_whose_only_bed_is_being_cleaned_is_not_available():
    occupancy = occupancy_of(room(), [BedStatus.PENDING_CLEANING])

    assert occupancy.status is RoomStatus.PENDING_CLEANING
    assert (occupancy.beds, occupancy.cleaning, occupancy.available) == (1, 1, 0)


def test_one_free_bed_is_enough_for_the_room_to_be_available():
    occupancy = occupancy_of(
        room(), [BedStatus.OCCUPIED, BedStatus.PENDING_CLEANING, BedStatus.AVAILABLE]
    )

    assert occupancy.status is RoomStatus.AVAILABLE
    assert (occupancy.occupied, occupancy.cleaning, occupancy.available) == (1, 1, 1)


def test_a_full_room_is_occupied_and_a_reserved_one_is_reserved():
    assert occupancy_of(room(), [BedStatus.OCCUPIED, BedStatus.OCCUPIED]).status is (
        RoomStatus.OCCUPIED
    )
    assert occupancy_of(room(), [BedStatus.OCCUPIED, BedStatus.RESERVED]).status is (
        RoomStatus.RESERVED
    )


def test_a_room_with_every_bed_out_of_service_is_blocked():
    occupancy = occupancy_of(room(), [BedStatus.MAINTENANCE, BedStatus.OUT_OF_SERVICE])

    assert occupancy.status is RoomStatus.BLOCKED
    assert occupancy.unavailable == 2


def test_what_was_decided_about_the_room_itself_wins_over_its_beds():
    # Una habitación en mantenimiento no se usa aunque sus camas estén libres.
    assert occupancy_of(room(RoomStatus.MAINTENANCE), [BedStatus.AVAILABLE]).status is (
        RoomStatus.MAINTENANCE
    )
    assert occupancy_of(room(RoomStatus.BLOCKED), [BedStatus.AVAILABLE]).status is (
        RoomStatus.BLOCKED
    )


def test_a_room_without_beds_keeps_what_the_room_says():
    assert occupancy_of(room(), []).status is RoomStatus.AVAILABLE
    assert occupancy_of(room(RoomStatus.OCCUPIED), []).status is RoomStatus.OCCUPIED


@requires_postgres
def test_the_bed_statuses_of_each_room_are_read_in_one_query():
    async def case(factory):
        async with factory() as session:
            scenario = await build_scenario(session, beds=2)
            bed = await session.get(Bed, scenario.bed_ids[0])
            bed.status = BedStatus.PENDING_CLEANING
            await session.commit()
            room_id = bed.room_id
        async with factory() as session:
            by_room = await occupancy_by_room(session)
            statuses = sorted(status.value for status in by_room[room_id])
            stored = await session.get(Room, room_id)
            return statuses, occupancy_of(stored, by_room[room_id]).status

    statuses, derived = run_db(case)
    assert statuses == ["AVAILABLE", "PENDING_CLEANING"]
    assert derived is RoomStatus.AVAILABLE
