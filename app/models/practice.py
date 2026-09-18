"""Medical practice catalog as it is nomenclated in Argentina.

A practice is described twice: once as a *nomenclador* entry (code, chapter and the
units that the nomenclador assigns to it) and once as money, in ``medical_practice_tariffs``,
because the value of the same code changes per payer, per plan and over time.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.account import ChargeItem
from app.models.base import Base, TimestampMixin, UUIDMixin


class Nomenclador(str, enum.Enum):
    """Coding system the practice belongs to."""

    NACIONAL = "NACIONAL"  # Nomenclador Nacional de Prestaciones Médicas (Res. 39/94)
    NBU = "NBU"  # Nomenclador Bioquímico Único
    NU_SSS = "NU_SSS"  # Nomenclador Único de la Superintendencia de Servicios de Salud
    HPGD = "HPGD"  # Hospitales Públicos de Gestión Descentralizada
    PROPIO = "PROPIO"  # Nomenclador interno de la institución


class PracticeChapter(str, enum.Enum):
    """Capítulos del nomenclador."""

    CONSULTAS = "CONSULTAS"
    INTERNACION = "INTERNACION"
    PRACTICAS_ESPECIALIZADAS = "PRACTICAS_ESPECIALIZADAS"
    CIRUGIA = "CIRUGIA"
    OBSTETRICIA = "OBSTETRICIA"
    ANESTESIA = "ANESTESIA"
    LABORATORIO = "LABORATORIO"
    DIAGNOSTICO_POR_IMAGENES = "DIAGNOSTICO_POR_IMAGENES"
    ANATOMIA_PATOLOGICA = "ANATOMIA_PATOLOGICA"
    HEMOTERAPIA = "HEMOTERAPIA"
    KINESIOLOGIA = "KINESIOLOGIA"
    FONOAUDIOLOGIA = "FONOAUDIOLOGIA"
    SALUD_MENTAL = "SALUD_MENTAL"
    ODONTOLOGIA = "ODONTOLOGIA"
    TRASLADOS = "TRASLADOS"
    OTROS = "OTROS"


class PracticeType(str, enum.Enum):
    CONSULTA = "CONSULTA"
    PRACTICA = "PRACTICA"
    CIRUGIA = "CIRUGIA"
    LABORATORIO = "LABORATORIO"
    IMAGENES = "IMAGENES"
    ANESTESIA = "ANESTESIA"
    INTERNACION = "INTERNACION"
    MODULO = "MODULO"
    TRASLADO = "TRASLADO"
    OTRO = "OTRO"


class PracticeSetting(str, enum.Enum):
    """Ámbito en el que la práctica puede realizarse."""

    AMBULATORIO = "AMBULATORIO"
    INTERNACION = "INTERNACION"
    AMBOS = "AMBOS"


class MedicalPractice(UUIDMixin, TimestampMixin, Base):
    """Nomenclador entry. The units are the ones published by the nomenclador; the money
    they are worth lives in :class:`MedicalPracticeTariff`."""

    __tablename__ = "medical_practices"

    nomenclador: Mapped[Nomenclador] = mapped_column(
        Enum(Nomenclador, name="nomenclador"), index=True
    )
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    chapter: Mapped[PracticeChapter] = mapped_column(
        Enum(PracticeChapter, name="practice_chapter"), index=True
    )
    practice_type: Mapped[PracticeType] = mapped_column(Enum(PracticeType, name="practice_type"))
    setting: Mapped[PracticeSetting] = mapped_column(
        Enum(PracticeSetting, name="practice_setting"),
        default=PracticeSetting.AMBOS,
        server_default=PracticeSetting.AMBOS.value,
    )
    # Unidades del nomenclador: galeno (honorarios), gastos, anestesia, bioquímicas (UB)
    # y radiológicas (UR). Cada capítulo usa las que le corresponden y deja el resto en 0.
    galeno_units: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(0), server_default="0"
    )
    expense_units: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(0), server_default="0"
    )
    anesthesia_units: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(0), server_default="0"
    )
    biochemical_units: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(0), server_default="0"
    )
    radiology_units: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(0), server_default="0"
    )
    requires_authorization: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    requires_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    tariffs: Mapped[list["MedicalPracticeTariff"]] = relationship(
        back_populates="practice",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("nomenclador", "code", name="uq_medical_practices_nomenclador_code"),
        CheckConstraint("galeno_units >= 0", name="non_negative_galeno_units"),
        CheckConstraint("expense_units >= 0", name="non_negative_expense_units"),
        CheckConstraint("anesthesia_units >= 0", name="non_negative_anesthesia_units"),
        CheckConstraint("biochemical_units >= 0", name="non_negative_biochemical_units"),
        CheckConstraint("radiology_units >= 0", name="non_negative_radiology_units"),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="valid_period",
        ),
    )


class MedicalPracticeTariff(UUIDMixin, TimestampMixin, Base):
    """Agreed value of a practice. ``payer_id`` NULL is the institutional tariff, the one
    charged to a private patient with no payer behind."""

    __tablename__ = "medical_practice_tariffs"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("medical_practices.id", ondelete="CASCADE"), index=True
    )
    payer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payers.id", ondelete="RESTRICT"), index=True
    )
    health_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("health_plans.id", ondelete="RESTRICT"), index=True
    )
    # Valor de la unidad acordado con el financiador; honorarios y gastos son el resultado
    # de multiplicarlo por las unidades de la práctica, o un importe cerrado si se pactó así.
    unit_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    professional_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal(0), server_default="0"
    )
    expense_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal(0), server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    coinsurance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal(0), server_default="0"
    )
    currency: Mapped[str] = mapped_column(String(3), default="ARS", server_default="ARS")
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    practice: Mapped[MedicalPractice] = relationship(back_populates="tariffs")

    __table_args__ = (
        # One tariff per practice, payer, plan and start date. ``NULLS NOT DISTINCT`` so the
        # institutional tariff (payer_id NULL) cannot be loaded twice for the same date.
        Index(
            "uq_medical_practice_tariffs_scope_valid_from",
            "practice_id",
            "payer_id",
            "health_plan_id",
            "valid_from",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("unit_value IS NULL OR unit_value >= 0", name="non_negative_unit_value"),
        CheckConstraint("professional_fee >= 0", name="non_negative_professional_fee"),
        CheckConstraint("expense_amount >= 0", name="non_negative_expense_amount"),
        CheckConstraint("total_amount >= 0", name="non_negative_total_amount"),
        CheckConstraint("coinsurance >= 0", name="non_negative_coinsurance"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="valid_period",
        ),
    )


class PracticeOrderStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    PERFORMED = "PERFORMED"
    CANCELLED = "CANCELLED"


class HospitalizationPractice(UUIDMixin, TimestampMixin, Base):
    """A practice indicated during a hospitalization, and who indicated it.

    Prescribing and performing are different moments: the practice is registered as
    ``REQUESTED`` when it is only indicated, and it is the performance that turns it into
    a charge on the account of the hospitalization.
    """

    __tablename__ = "hospitalization_practices"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), index=True
    )
    practice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("medical_practices.id", ondelete="RESTRICT"), index=True
    )
    # Snapshot of the catalog entry, so the history of the hospitalization does not change
    # when the nomenclador is edited.
    practice_code: Mapped[str] = mapped_column(String(20))
    practice_name: Mapped[str] = mapped_column(String(250))
    prescribed_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("professionals.id", ondelete="RESTRICT"), index=True
    )
    performed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("professionals.id", ondelete="RESTRICT"), index=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), index=True
    )
    # The charge the performance generated. It stays here so the account and the clinical
    # record never drift apart.
    charge_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("charge_items.id", ondelete="SET NULL"), unique=True
    )
    status: Mapped[PracticeOrderStatus] = mapped_column(
        Enum(PracticeOrderStatus, name="practice_order_status"),
        default=PracticeOrderStatus.REQUESTED,
        server_default=PracticeOrderStatus.REQUESTED.value,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(1), server_default="1")
    prescribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indication: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    practice: Mapped[MedicalPractice] = relationship()
    charge_item: Mapped[ChargeItem | None] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        Index(
            "ix_hospitalization_practices_hospitalization_prescribed",
            "hospitalization_id",
            "prescribed_at",
        ),
    )
