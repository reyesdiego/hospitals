import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class AdmissionOrigin(str, enum.Enum):
    EMERGENCY_ROOM = "EMERGENCY_ROOM"
    OUTPATIENT_CLINIC = "OUTPATIENT_CLINIC"
    SCHEDULED_SURGERY = "SCHEDULED_SURGERY"
    EXTERNAL_REFERRAL = "EXTERNAL_REFERRAL"
    HOME_HOSPITALIZATION = "HOME_HOSPITALIZATION"
    SPECIAL_CARE_UNIT = "SPECIAL_CARE_UNIT"
    SCHEDULED_MEDICAL_ORDER = "SCHEDULED_MEDICAL_ORDER"


class AdmissionType(str, enum.Enum):
    PRE_ADMISSION = "PRE_ADMISSION"
    SCHEDULED = "SCHEDULED"
    EMERGENCY = "EMERGENCY"


class AdmissionStatus(str, enum.Enum):
    PRE_ADMITTED = "PRE_ADMITTED"
    PENDING_AUTHORIZATION = "PENDING_AUTHORIZATION"
    PENDING_BED = "PENDING_BED"
    ADMITTED = "ADMITTED"
    ADMINISTRATIVE_DISCHARGE = "ADMINISTRATIVE_DISCHARGE"
    CANCELLED = "CANCELLED"


class AuthorizationStatus(str, enum.Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"


class EpisodeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ConsentType(str, enum.Enum):
    GENERAL_ADMISSION = "GENERAL_ADMISSION"
    DATA_PROCESSING = "DATA_PROCESSING"
    PROCEDURE = "PROCEDURE"
    ANESTHESIA = "ANESTHESIA"
    TRANSFER = "TRANSFER"


class PatientCoverage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "patient_coverages"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    payer_name: Mapped[str] = mapped_column(String(150))
    plan_name: Mapped[str | None] = mapped_column(String(150))
    member_number: Mapped[str | None] = mapped_column(String(80))
    authorization_required: Mapped[bool] = mapped_column(Boolean, default=False)


class Episode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "episodes"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    episode_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[EpisodeStatus] = mapped_column(
        Enum(EpisodeStatus, name="episode_status"), default=EpisodeStatus.OPEN
    )
    reason: Mapped[str] = mapped_column(String(500))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Admission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "admissions"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="RESTRICT"), index=True
    )
    hospitalization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    coverage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patient_coverages.id", ondelete="RESTRICT"), index=True
    )
    requesting_service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), index=True
    )
    requested_bed_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("beds.id", ondelete="RESTRICT"), index=True
    )
    origin: Mapped[AdmissionOrigin] = mapped_column(Enum(AdmissionOrigin, name="admission_origin"))
    admission_type: Mapped[AdmissionType] = mapped_column(
        Enum(AdmissionType, name="admission_type")
    )
    status: Mapped[AdmissionStatus] = mapped_column(
        Enum(AdmissionStatus, name="admission_status"), default=AdmissionStatus.PRE_ADMITTED
    )
    identity_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    authorization_status: Mapped[AuthorizationStatus] = mapped_column(
        Enum(AuthorizationStatus, name="authorization_status"),
        default=AuthorizationStatus.NOT_REQUIRED,
    )
    authorization_number: Mapped[str | None] = mapped_column(String(100))
    responsible_contact_name: Mapped[str] = mapped_column(String(150))
    responsible_contact_phone: Mapped[str] = mapped_column(String(80))
    responsible_contact_relationship: Mapped[str | None] = mapped_column(String(80))
    admission_reason: Mapped[str] = mapped_column(String(500))
    responsible_physician: Mapped[str] = mapped_column(String(150))
    presumptive_diagnosis: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    administrative_discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_admissions_patient_status_type",
            "patient_id",
            "status",
            "admission_type",
        ),
    )


class AdmissionConsent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "admission_consents"

    admission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admissions.id", ondelete="CASCADE"), index=True
    )
    consent_type: Mapped[ConsentType] = mapped_column(Enum(ConsentType, name="consent_type"))
    signed_by: Mapped[str] = mapped_column(String(150))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
