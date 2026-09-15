import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class BedStatus(str, enum.Enum):
    AVAILABLE="AVAILABLE"; RESERVED="RESERVED"; OCCUPIED="OCCUPIED"; PENDING_CLEANING="PENDING_CLEANING"; BLOCKED="BLOCKED"; MAINTENANCE="MAINTENANCE"
class TransferStatus(str, enum.Enum):
    COMPLETED="COMPLETED"; CANCELLED="CANCELLED"
class Bed(UUIDMixin, TimestampMixin, Base):
    __tablename__="beds"
    facility_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str]=mapped_column(String(50))
    ward: Mapped[str]=mapped_column(String(100))
    status: Mapped[BedStatus]=mapped_column(
        Enum(BedStatus,name="bed_status"),
        default=BedStatus.AVAILABLE,
        server_default=BedStatus.AVAILABLE.value,
    )
    room_id: Mapped[uuid.UUID]=mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    __table_args__=(Index("uq_beds_facility_code","facility_id","code",unique=True),)
class BedAssignment(UUIDMixin, TimestampMixin, Base):
    __tablename__="bed_assignments"
    hospitalization_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True)
    bed_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("beds.id", ondelete="RESTRICT"), index=True)
    status: Mapped[BedStatus]=mapped_column(Enum(BedStatus,name="bed_status"))
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    assignment_reason: Mapped[str|None]=mapped_column(String(500))
    assigned_by: Mapped[str|None]=mapped_column(String(150))
    ended_by: Mapped[str|None]=mapped_column(String(150))
    __table_args__=(
      Index("uq_active_assignment_per_bed","bed_id",unique=True,postgresql_where=text("ended_at IS NULL")),
      Index("uq_active_bed_per_hospitalization","hospitalization_id",unique=True,postgresql_where=text("hospitalization_id IS NOT NULL AND ended_at IS NULL")),
    )


class BedTransfer(UUIDMixin, TimestampMixin, Base):
    __tablename__="bed_transfers"
    hospitalization_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True)
    from_bed_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("beds.id", ondelete="RESTRICT"), index=True)
    to_bed_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("beds.id", ondelete="RESTRICT"), index=True)
    status: Mapped[TransferStatus]=mapped_column(Enum(TransferStatus,name="bed_transfer_status"))
    requested_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    reason: Mapped[str|None]=mapped_column(String(500))
    requested_by: Mapped[str|None]=mapped_column(String(150))
    completed_by: Mapped[str|None]=mapped_column(String(150))
