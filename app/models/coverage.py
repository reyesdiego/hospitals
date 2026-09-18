import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CoverageStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"


class Payer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payers"

    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(30), unique=True)
    tax_id: Mapped[str | None] = mapped_column(String(40))

    health_plans: Mapped[list["HealthPlan"]] = relationship(back_populates="payer")


class HealthPlan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "health_plans"
    __table_args__ = (UniqueConstraint("payer_id", "code", name="uq_health_plans_payer_code"),)

    payer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payers.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(40))

    payer: Mapped[Payer] = relationship(back_populates="health_plans")


class PatientCoverage(UUIDMixin, TimestampMixin, Base):
    """Coverage is patient information; it is not an authorization."""

    __tablename__ = "patient_coverages"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    payer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payers.id", ondelete="RESTRICT"), index=True
    )
    health_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("health_plans.id", ondelete="RESTRICT"), index=True
    )
    # Snapshot of the payer/plan names. Filled from payer_id/health_plan_id when those are
    # informed, kept as free text for coverages loaded without a registered payer.
    payer_name: Mapped[str] = mapped_column(String(150))
    plan_name: Mapped[str | None] = mapped_column(String(150))
    member_number: Mapped[str | None] = mapped_column(String(80))
    authorization_required: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[CoverageStatus] = mapped_column(
        Enum(CoverageStatus, name="coverage_status"),
        default=CoverageStatus.ACTIVE,
        server_default=CoverageStatus.ACTIVE.value,
    )

    payer: Mapped[Payer | None] = relationship()
    health_plan: Mapped[HealthPlan | None] = relationship()
