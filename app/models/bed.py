import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class BedStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    PENDING_CLEANING = "PENDING_CLEANING"
    CLEANING = "CLEANING"
    BLOCKED = "BLOCKED"
    MAINTENANCE = "MAINTENANCE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class TransferStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class BedReservationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


#: Statuses that a bed may be moved to through the operational status endpoints.
OPERATIONAL_BED_STATUSES = {
    BedStatus.AVAILABLE,
    BedStatus.PENDING_CLEANING,
    BedStatus.CLEANING,
    BedStatus.BLOCKED,
    BedStatus.MAINTENANCE,
    BedStatus.OUT_OF_SERVICE,
}


class Bed(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "beds"

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50))
    ward: Mapped[str] = mapped_column(String(100))
    status: Mapped[BedStatus] = mapped_column(
        Enum(BedStatus, name="bed_status"),
        default=BedStatus.AVAILABLE,
        server_default=BedStatus.AVAILABLE.value,
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    __table_args__ = (Index("uq_beds_facility_code", "facility_id", "code", unique=True),)


class BedReservation(UUIDMixin, TimestampMixin, Base):
    """A hold on a bed before the patient physically occupies it. Reservation != occupancy."""

    __tablename__ = "bed_reservations"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    bed_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("beds.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[BedReservationStatus] = mapped_column(
        Enum(BedReservationStatus, name="bed_reservation_status"),
        default=BedReservationStatus.ACTIVE,
    )
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reserved_by: Mapped[str | None] = mapped_column(String(150))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index(
            "uq_active_reservation_per_bed",
            "bed_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_active_reservation_per_hospitalization",
            "hospitalization_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > reserved_at",
            name="expiry_after_reservation",
        ),
    )


class BedAssignment(UUIDMixin, TimestampMixin, Base):
    """Historical physical occupancy of a bed by a hospitalization.
    Active assignment: ``ended_at IS NULL``."""

    __tablename__ = "bed_assignments"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    bed_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("beds.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignment_reason: Mapped[str | None] = mapped_column(String(500))
    assigned_by: Mapped[str | None] = mapped_column(String(150))
    ended_by: Mapped[str | None] = mapped_column(String(150))

    __table_args__ = (
        Index(
            "uq_active_assignment_per_bed",
            "bed_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index(
            "uq_active_bed_per_hospitalization",
            "hospitalization_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="period",
        ),
    )


class BedStatusHistory(UUIDMixin, TimestampMixin, Base):
    """Append-only log of bed status changes; feeds turnaround-time metrics."""

    __tablename__ = "bed_status_history"

    bed_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("beds.id", ondelete="CASCADE"), index=True
    )
    previous_status: Mapped[BedStatus | None] = mapped_column(Enum(BedStatus, name="bed_status"))
    new_status: Mapped[BedStatus] = mapped_column(Enum(BedStatus, name="bed_status"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_by: Mapped[str | None] = mapped_column(String(150))
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_bed_status_history_bed_changed", "bed_id", "changed_at"),)


class BedTransfer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bed_transfers"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    from_bed_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("beds.id", ondelete="RESTRICT"), index=True
    )
    to_bed_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("beds.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, name="bed_transfer_status")
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))
    requested_by: Mapped[str | None] = mapped_column(String(150))
    completed_by: Mapped[str | None] = mapped_column(String(150))
