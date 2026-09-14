import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Specialty(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "specialties"

    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(30), unique=True)

    professional_links: Mapped[list["ProfessionalSpecialty"]] = relationship(
        back_populates="specialty",
    )


class Professional(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "professionals"
    __table_args__ = (
        UniqueConstraint("document_type", "document_number", name="uq_professionals_document"),
    )

    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    document_type: Mapped[str] = mapped_column(String(30))
    document_number: Mapped[str] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(80))

    specialty_links: Mapped[list["ProfessionalSpecialty"]] = relationship(
        back_populates="professional",
        cascade="all, delete-orphan",
    )

    @property
    def specialties(self) -> list["ProfessionalSpecialty"]:
        return self.specialty_links


class ProfessionalSpecialty(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "professional_specialties"
    __table_args__ = (
        UniqueConstraint(
            "professional_id",
            "specialty_id",
            name="uq_professional_specialties_professional_specialty",
        ),
        UniqueConstraint("license_number", name="uq_professional_specialties_license_number"),
    )

    professional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE")
    )
    specialty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT")
    )
    license_number: Mapped[str] = mapped_column(String(80))

    professional: Mapped[Professional] = relationship(back_populates="specialty_links")
    specialty: Mapped[Specialty] = relationship(back_populates="professional_links")
