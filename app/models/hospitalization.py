import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.admission import AdmissionType
from app.models.base import Base, TimestampMixin, UUIDMixin


class HospitalizationStatus(str, enum.Enum):
    PENDING_BED = "PENDING_BED"
    IN_PROGRESS = "IN_PROGRESS"
    DISCHARGE_PLANNED = "DISCHARGE_PLANNED"
    CLINICALLY_DISCHARGED = "CLINICALLY_DISCHARGED"
    ADMINISTRATIVELY_DISCHARGED = "ADMINISTRATIVELY_DISCHARGED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


#: Statuses where the patient is still under the responsibility of the hospital.
OPEN_HOSPITALIZATION_STATUSES = {
    HospitalizationStatus.PENDING_BED,
    HospitalizationStatus.IN_PROGRESS,
    HospitalizationStatus.DISCHARGE_PLANNED,
}
#: Statuses where clinical care is still being provided.
CLINICALLY_ACTIVE_STATUSES = {
    HospitalizationStatus.IN_PROGRESS,
    HospitalizationStatus.DISCHARGE_PLANNED,
}


class Hospitalization(UUIDMixin, TimestampMixin, Base):
    """Inpatient process. Time-varying relations live in their own historical tables."""

    __tablename__ = "hospitalizations"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="RESTRICT"), index=True
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("facilities.id", ondelete="RESTRICT"), index=True
    )
    admission_type: Mapped[AdmissionType | None] = mapped_column(
        Enum(AdmissionType, name="admission_type")
    )
    status: Mapped[HospitalizationStatus] = mapped_column(
        Enum(HospitalizationStatus, name="hospitalization_status"),
        default=HospitalizationStatus.PENDING_BED,
    )
    admission_reason: Mapped[str] = mapped_column(String(500))
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clinically_discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    physically_departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    administratively_discharged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HospitalizationServiceAssignment(UUIDMixin, TimestampMixin, Base):
    """History of the service responsible for the patient. Active row: ``ended_at IS NULL``."""

    __tablename__ = "hospitalization_service_assignments"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        # Explicit name: the convention-generated one exceeds the 63-char PostgreSQL limit.
        ForeignKey(
            "hospitalizations.id",
            ondelete="RESTRICT",
            name="fk_hosp_service_assignments_hospitalization_id",
        ),
        index=True,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))
    assigned_by: Mapped[str | None] = mapped_column(String(150))

    __table_args__ = (
        Index(
            "uq_active_service_per_hospitalization",
            "hospitalization_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )
