import enum, uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin
class BedStatus(str, enum.Enum):
    AVAILABLE="AVAILABLE"; RESERVED="RESERVED"; OCCUPIED="OCCUPIED"; PENDING_CLEANING="PENDING_CLEANING"; BLOCKED="BLOCKED"; MAINTENANCE="MAINTENANCE"
class Bed(UUIDMixin, TimestampMixin, Base):
    __tablename__="beds"
    facility_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str]=mapped_column(String(50))
    ward: Mapped[str]=mapped_column(String(100))
    room_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    __table_args__=(Index("uq_beds_facility_code","facility_id","code",unique=True),)
class BedAssignment(UUIDMixin, TimestampMixin, Base):
    __tablename__="bed_assignments"
    hospitalization_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True)
    bed_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("beds.id", ondelete="RESTRICT"), index=True)
    status: Mapped[BedStatus]=mapped_column(Enum(BedStatus,name="bed_status"))
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(
      Index("uq_active_assignment_per_bed","bed_id",unique=True,postgresql_where=text("ended_at IS NULL")),
      Index("uq_active_bed_per_hospitalization","hospitalization_id",unique=True,postgresql_where=text("hospitalization_id IS NOT NULL AND ended_at IS NULL")),
    )
