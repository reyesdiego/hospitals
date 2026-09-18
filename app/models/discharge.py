import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class DischargeDestination(str, enum.Enum):
    HOME = "HOME"
    OTHER_FACILITY = "OTHER_FACILITY"
    HOME_CARE = "HOME_CARE"
    REHABILITATION = "REHABILITATION"
    OTHER = "OTHER"


class DischargePlanStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class DischargeType(str, enum.Enum):
    MEDICAL = "MEDICAL"
    VOLUNTARY = "VOLUNTARY"
    TRANSFER = "TRANSFER"
    DECEASED = "DECEASED"
    ABSCONDED = "ABSCONDED"
    OTHER = "OTHER"


ACTIVE_DISCHARGE_PLAN_STATUSES = {
    DischargePlanStatus.PLANNED,
    DischargePlanStatus.CONFIRMED,
}


class DischargePlan(UUIDMixin, TimestampMixin, Base):
    """Discharge planning. Planning does not release the bed nor end the hospitalization."""

    __tablename__ = "discharge_plans"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    planned_date: Mapped[date | None] = mapped_column(Date)
    destination: Mapped[DischargeDestination] = mapped_column(
        Enum(DischargeDestination, name="discharge_destination")
    )
    requires_transport: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_home_care: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[DischargePlanStatus] = mapped_column(
        Enum(DischargePlanStatus, name="discharge_plan_status"),
        default=DischargePlanStatus.PLANNED,
    )
    created_by: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_active_discharge_plan_per_hospitalization",
            "hospitalization_id",
            unique=True,
            postgresql_where=text("status IN ('PLANNED', 'CONFIRMED')"),
        ),
    )


class Discharge(UUIDMixin, TimestampMixin, Base):
    """Clinical discharge. It does not release the bed and it is not the administrative discharge."""

    __tablename__ = "discharges"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), unique=True
    )
    discharge_type: Mapped[DischargeType] = mapped_column(
        Enum(DischargeType, name="discharge_type")
    )
    discharge_reason: Mapped[str | None] = mapped_column(String(500))
    destination: Mapped[DischargeDestination | None] = mapped_column(
        Enum(DischargeDestination, name="discharge_destination")
    )
    ordered_by: Mapped[str | None] = mapped_column(String(150))
    ordered_by_practitioner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("professionals.id", ondelete="RESTRICT"), index=True
    )
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    instructions: Mapped[str | None] = mapped_column(Text)
