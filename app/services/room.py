import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.bed import Bed
from app.models.facility import Facility
from app.models.room import Room
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
