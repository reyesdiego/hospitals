import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class AuthorizationType(str, enum.Enum):
    ADMISSION = "ADMISSION"
    EXTENSION = "EXTENSION"
    PROCEDURE = "PROCEDURE"
    TRANSFER = "TRANSFER"
    OTHER = "OTHER"


class AuthorizationState(str, enum.Enum):
    REQUESTED = "REQUESTED"
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


OPEN_AUTHORIZATION_STATES = {AuthorizationState.REQUESTED, AuthorizationState.PENDING}
RESOLVED_AUTHORIZATION_STATES = {
    AuthorizationState.AUTHORIZED,
    AuthorizationState.REJECTED,
    AuthorizationState.EXPIRED,
    AuthorizationState.CANCELLED,
}


class Authorization(UUIDMixin, TimestampMixin, Base):
    """One authorization request/response. A hospitalization may need several of them."""

    __tablename__ = "authorizations"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    admission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admissions.id", ondelete="RESTRICT"), index=True
    )
    hospitalization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    patient_coverage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patient_coverages.id", ondelete="RESTRICT"), index=True
    )
    authorization_type: Mapped[AuthorizationType] = mapped_column(
        Enum(AuthorizationType, name="authorization_type")
    )
    authorization_number: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[AuthorizationState] = mapped_column(
        Enum(AuthorizationState, name="authorization_state"),
        default=AuthorizationState.REQUESTED,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str | None] = mapped_column(String(150))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
