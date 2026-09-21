import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class HospitalizationEventType(str, enum.Enum):
    ADMISSION_REQUESTED = "ADMISSION_REQUESTED"
    ADMISSION_AUTHORIZED = "ADMISSION_AUTHORIZED"
    ADMISSION_REJECTED = "ADMISSION_REJECTED"
    HOSPITALIZATION_CREATED = "HOSPITALIZATION_CREATED"
    SERVICE_ASSIGNED = "SERVICE_ASSIGNED"
    CARE_TEAM_MEMBER_ASSIGNED = "CARE_TEAM_MEMBER_ASSIGNED"
    CARE_TEAM_MEMBER_ENDED = "CARE_TEAM_MEMBER_ENDED"
    BED_RESERVED = "BED_RESERVED"
    BED_RESERVATION_CANCELLED = "BED_RESERVATION_CANCELLED"
    BED_RESERVATION_EXPIRED = "BED_RESERVATION_EXPIRED"
    BED_ASSIGNED = "BED_ASSIGNED"
    PATIENT_TRANSFERRED = "PATIENT_TRANSFERRED"
    BED_RELEASED = "BED_RELEASED"
    PRACTICE_ORDERED = "PRACTICE_ORDERED"
    PRACTICE_PERFORMED = "PRACTICE_PERFORMED"
    PRACTICE_CANCELLED = "PRACTICE_CANCELLED"
    DISCHARGE_PLANNED = "DISCHARGE_PLANNED"
    CLINICAL_DISCHARGE_COMPLETED = "CLINICAL_DISCHARGE_COMPLETED"
    PATIENT_PHYSICALLY_DEPARTED = "PATIENT_PHYSICALLY_DEPARTED"
    BED_CLEANING_STARTED = "BED_CLEANING_STARTED"
    BED_AVAILABLE = "BED_AVAILABLE"
    BED_STATUS_CHANGED = "BED_STATUS_CHANGED"
    ADMINISTRATIVE_DISCHARGE_COMPLETED = "ADMINISTRATIVE_DISCHARGE_COMPLETED"
    CHARGE_ITEM_VOIDED = "CHARGE_ITEM_VOIDED"
    PAYMENT_REGISTERED = "PAYMENT_REGISTERED"
    PAYMENT_VOIDED = "PAYMENT_VOIDED"
    ACCOUNT_READY_FOR_REVIEW = "ACCOUNT_READY_FOR_REVIEW"
    HOSPITALIZATION_CLOSED = "HOSPITALIZATION_CLOSED"
    HOSPITALIZATION_CANCELLED = "HOSPITALIZATION_CANCELLED"
    #: Un administrador modificó una internación que ya tenía alta médica.
    POST_DISCHARGE_CHANGE = "POST_DISCHARGE_CHANGE"


class HospitalizationEvent(UUIDMixin, TimestampMixin, Base):
    """Append-only audit trail of the admission/hospitalization/bed lifecycle."""

    __tablename__ = "hospitalization_events"

    event_type: Mapped[HospitalizationEventType] = mapped_column(
        Enum(HospitalizationEventType, name="hospitalization_event_type")
    )
    hospitalization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    admission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admissions.id", ondelete="RESTRICT"), index=True
    )
    bed_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("beds.id", ondelete="RESTRICT"), index=True
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str | None] = mapped_column(String(150))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_hospitalization_events_hospitalization_occurred", "hospitalization_id", "occurred_at"),
    )
