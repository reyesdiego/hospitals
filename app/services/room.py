import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.bed import Bed, BedStatus
from app.models.facility import Facility
from app.models.room import Room, RoomStatus
from app.schemas.domain import BedCreate, BedRoomAssignmentCreate, BedUpdate, RoomCreate, RoomUpdate


class RoomService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_room(self, payload: RoomCreate) -> Room:
        await self._require_facility(payload.facility_id)
        room = Room(**payload.model_dump())
        self.session.add(room)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DomainError("Código de habitación duplicado para el centro", 409) from exc
        await self.session.refresh(room)
        return room

    async def update_room(self, room_id: uuid.UUID, payload: RoomUpdate) -> Room:
        room = await self.session.get(Room, room_id)
        if not room:
            raise DomainError("Habitación inexistente", 404)
        await self._require_facility(payload.facility_id)
        room.facility_id = payload.facility_id
        room.code = payload.code
        room.ward = payload.ward
        room.status = payload.status
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DomainError("Código de habitación duplicado para el centro", 409) from exc
        await self.session.refresh(room)
        return room

    async def delete_room(self, room_id: uuid.UUID) -> None:
        room = await self.session.get(Room, room_id)
        if not room:
            raise DomainError("Habitación inexistente", 404)
        bed_exists = await self.session.scalar(select(Bed.id).where(Bed.room_id == room_id).limit(1))
        if bed_exists:
            raise DomainError("La habitación tiene camas asociadas", 409)
        await self.session.delete(room)
        await self.session.commit()

    async def create_bed(self, payload: BedCreate) -> Bed:
        room = await self._require_room_for_facility(payload.room_id, payload.facility_id)
        bed = Bed(
            facility_id=payload.facility_id,
            room_id=payload.room_id,
            ward=room.ward,
            code=payload.code,
        )
        self.session.add(bed)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DomainError("Código de cama duplicado para el centro", 409) from exc
        await self.session.refresh(bed)
        return bed

    async def update_bed(self, bed_id: uuid.UUID, payload: BedUpdate) -> Bed:
        bed = await self.session.get(Bed, bed_id)
        if not bed:
            raise DomainError("Cama inexistente", 404)
        room = await self._require_room_for_facility(payload.room_id, payload.facility_id)
        bed.facility_id = payload.facility_id
        bed.room_id = payload.room_id
        bed.ward = room.ward
        bed.code = payload.code
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DomainError("Código de cama duplicado para el centro", 409) from exc
        await self.session.refresh(bed)
        return bed

    async def assign_bed_room(self, bed_id: uuid.UUID, payload: BedRoomAssignmentCreate) -> Bed:
        bed = await self.session.get(Bed, bed_id)
        if not bed:
            raise DomainError("Cama inexistente", 404)
        room = await self._require_room_for_facility(payload.room_id, bed.facility_id)
        bed.room_id = room.id
        bed.ward = room.ward
        await self.session.commit()
        await self.session.refresh(bed)
        return bed

    async def _require_facility(self, facility_id: uuid.UUID) -> Facility:
        facility = await self.session.get(Facility, facility_id)
        if not facility:
            raise DomainError("Centro sanitario inexistente", 404)
        return facility

    async def _require_room_for_facility(self, room_id: uuid.UUID, facility_id: uuid.UUID) -> Room:
        room = await self.session.get(Room, room_id)
        if not room:
            raise DomainError("Habitación inexistente", 404)
        if room.facility_id != facility_id:
            raise DomainError("La habitación no pertenece al centro informado", 422)
        return room


#: Estado que muestra la habitación según sus camas, del más disponible al menos.
#: BLOQUEADA y MANTENIMIENTO se deciden sobre la habitación misma, así que pisan lo demás.
ROOM_STATUS_BY_BEDS: list[tuple[set[BedStatus], RoomStatus]] = [
    ({BedStatus.AVAILABLE}, RoomStatus.AVAILABLE),
    ({BedStatus.RESERVED}, RoomStatus.RESERVED),
    ({BedStatus.OCCUPIED}, RoomStatus.OCCUPIED),
    ({BedStatus.PENDING_CLEANING, BedStatus.CLEANING}, RoomStatus.PENDING_CLEANING),
]

ADMINISTRATIVE_ROOM_STATUSES = {RoomStatus.BLOCKED, RoomStatus.MAINTENANCE}


@dataclass(frozen=True)
class RoomOccupancy:
    """Cómo está la habitación según sus camas."""

    status: RoomStatus
    beds: int = 0
    available: int = 0
    reserved: int = 0
    occupied: int = 0
    cleaning: int = 0
    unavailable: int = 0


def occupancy_of(room: Room, bed_statuses: list[BedStatus]) -> RoomOccupancy:
    """El estado de una habitación es el de sus camas: es donde entra o no un paciente.

    Sin camas no hay nada que derivar y vale lo que diga la habitación; una habitación
    bloqueada o en mantenimiento lo está aunque sus camas estén libres.
    """

    counts = Counter(bed_statuses)
    derived = room.status
    if room.status not in ADMINISTRATIVE_ROOM_STATUSES and bed_statuses:
        derived = RoomStatus.BLOCKED  # todas las camas fuera de servicio
        for statuses, room_status in ROOM_STATUS_BY_BEDS:
            if any(counts[status] for status in statuses):
                derived = room_status
                break
    return RoomOccupancy(
        status=derived,
        beds=len(bed_statuses),
        available=counts[BedStatus.AVAILABLE],
        reserved=counts[BedStatus.RESERVED],
        occupied=counts[BedStatus.OCCUPIED],
        cleaning=counts[BedStatus.PENDING_CLEANING] + counts[BedStatus.CLEANING],
        unavailable=(
            counts[BedStatus.BLOCKED]
            + counts[BedStatus.MAINTENANCE]
            + counts[BedStatus.OUT_OF_SERVICE]
        ),
    )


async def occupancy_by_room(
    session: AsyncSession,
    room_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, list[BedStatus]]:
    """Estados de las camas de cada habitación, en una sola consulta."""

    stmt = select(Bed.room_id, Bed.status)
    if room_ids is not None:
        stmt = stmt.where(Bed.room_id.in_(room_ids))
    by_room: dict[uuid.UUID, list[BedStatus]] = defaultdict(list)
    for room_id, status in (await session.execute(stmt)).all():
        by_room[room_id].append(status)
    return by_room
