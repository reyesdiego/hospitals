import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class PatientIdentifierType(str, enum.Enum):
    DNI = "DNI"
    PASSPORT = "PASSPORT"
    MEDICAL_RECORD_NUMBER = "MEDICAL_RECORD_NUMBER"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    EXTERNAL = "EXTERNAL"
    OTHER = "OTHER"


class Patient(UUIDMixin, TimestampMixin, Base):
    __tablename__="patients"
    __table_args__=(UniqueConstraint("document_type","document_number",name="uq_patients_document"),)
    first_name: Mapped[str]=mapped_column(String(100))
    last_name: Mapped[str]=mapped_column(String(100))
    document_type: Mapped[str]=mapped_column(String(30))
    document_number: Mapped[str]=mapped_column(String(50))
    birth_date: Mapped[date|None]=mapped_column(Date)

    identifiers: Mapped[list["PatientIdentifier"]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
    )
    contacts: Mapped[list["PatientContact"]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
    )


class PatientIdentifier(UUIDMixin, TimestampMixin, Base):
    """External identity of a patient. The internal identity is always ``patients.id``."""

    __tablename__ = "patient_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "value",
            name="uq_patient_identifiers_type_value",
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    identifier_type: Mapped[PatientIdentifierType] = mapped_column(
        Enum(PatientIdentifierType, name="patient_identifier_type")
    )
    value: Mapped[str] = mapped_column(String(80), index=True)
    issuer: Mapped[str | None] = mapped_column(String(120))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    patient: Mapped[Patient] = relationship(back_populates="identifiers")


class PatientContact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "patient_contacts"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(150))
    relationship_to_patient: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(150))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    patient: Mapped[Patient] = relationship(back_populates="contacts")
