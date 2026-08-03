import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class RoomStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    PENDING_CLEANING = "PENDING_CLEANING"
    BLOCKED = "BLOCKED"
    MAINTENANCE = "MAINTENANCE"


class Room(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rooms"

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50))
    ward: Mapped[str] = mapped_column(String(100))
    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, name="room_status"),
        default=RoomStatus.AVAILABLE,
    )

    __table_args__ = (Index("uq_rooms_facility_code", "facility_id", "code", unique=True),)
