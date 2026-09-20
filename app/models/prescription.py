"""Recetas e indicaciones que el paciente se lleva al irse de alta."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.practice import MedicalPractice


class PrescriptionKind(str, enum.Enum):
    MEDICATION = "MEDICATION"  # receta: qué tomar y cómo
    PRACTICE = "PRACTICE"  # indicación: qué estudio o práctica hacerse


class DischargePrescription(UUIDMixin, TimestampMixin, Base):
    """Un renglón de lo que se le indica al paciente para después del alta.

    Medicación e indicaciones de prácticas viven en la misma tabla porque son el mismo acto
    —lo que el médico escribe al dar el alta— y se imprimen en el mismo documento, cada una
    en su sección.
    """

    __tablename__ = "discharge_prescriptions"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[PrescriptionKind] = mapped_column(Enum(PrescriptionKind, name="prescription_kind"))
    # Las prácticas del nomenclador se eligen del catálogo; la medicación es texto, porque
    # el vademécum no es parte de este sistema.
    practice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("medical_practices.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[str] = mapped_column(String(250))
    presentation: Mapped[str | None] = mapped_column(String(150))
    dosage: Mapped[str | None] = mapped_column(String(250))
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(1), server_default="1"
    )
    duration_days: Mapped[int | None] = mapped_column()
    instructions: Mapped[str | None] = mapped_column(Text)
    # Quién la firma: el profesional responsable y el usuario que la cargó.
    prescribed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("professionals.id", ondelete="RESTRICT"), index=True
    )
    prescribed_by_user_name: Mapped[str | None] = mapped_column(String(150))
    prescribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    practice: Mapped[MedicalPractice | None] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint(
            "duration_days IS NULL OR duration_days > 0", name="positive_duration"
        ),
        Index(
            "ix_discharge_prescriptions_hospitalization_kind",
            "hospitalization_id",
            "kind",
        ),
    )
