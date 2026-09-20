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
    Integer,
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
    # La indica el médico y la ejecuta enfermería: inyectables, medicación, extracciones,
    # colocación de Holter. Es lo que la hace aparecer en el panel de enfermería.
    is_nursing_task: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Carencia con la que se incorpora la práctica a cualquier plan. Cada plan puede pactar
    # la suya en :class:`HealthPlanPractice`; esta es la que rige mientras no lo haga.
    default_waiting_period_days: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
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
        CheckConstraint("default_waiting_period_days >= 0", name="non_negative_waiting_period"),
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


class HealthPlanPractice(UUIDMixin, TimestampMixin, Base):
    """What a plan covers of a practice: the cartilla of the plan.

    A practice is covered by a plan when it has a row here. ``is_covered`` False keeps the
    row instead of deleting it, because "this plan does not cover this practice" is an answer
    the front desk needs, and it is not the same as "nobody loaded it yet".
    """

    __tablename__ = "health_plan_practices"

    health_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("health_plans.id", ondelete="CASCADE"), index=True
    )
    practice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("medical_practices.id", ondelete="RESTRICT"), index=True
    )
    is_covered: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Días que deben pasar desde el alta de la cobertura del afiliado para poder usarla.
    # Vacío significa que el plan no pactó nada y rige la carencia de la práctica.
    waiting_period_days: Mapped[int | None] = mapped_column(Integer)
    copayment_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal(0), server_default="0"
    )
    # Lo que exige el plan, que no es lo mismo que el ``requires_authorization`` del
    # nomenclador: una práctica sin requisito clínico puede necesitar orden del financiador.
    requires_authorization: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    notes: Mapped[str | None] = mapped_column(Text)

    practice: Mapped[MedicalPractice] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "health_plan_id", "practice_id", name="uq_health_plan_practices_plan_practice"
        ),
        CheckConstraint(
            "waiting_period_days IS NULL OR waiting_period_days >= 0",
            name="non_negative_waiting_period",
        ),
        CheckConstraint("copayment_amount >= 0", name="non_negative_copayment"),
    )


class PlanCoverageStatus(str, enum.Enum):
    """Por qué la cartilla deja pasar (o no) una práctica."""

    NO_COVERAGE = "NO_COVERAGE"  # paciente particular: no hay cobertura
    NO_PLAN = "NO_PLAN"  # hay cobertura, pero no apunta a un plan del catálogo
    NO_CARTILLA = "NO_CARTILLA"  # el plan no tiene cartilla cargada todavía
    NOT_LISTED = "NOT_LISTED"  # hay cartilla y la práctica no está en ella
    NOT_COVERED = "NOT_COVERED"  # está en la cartilla y el plan la excluye
    WAITING_PERIOD = "WAITING_PERIOD"  # la carencia todavía no se cumplió
    COVERED = "COVERED"


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
    # Quién la dio por realizada en el sistema. Es otra cosa que ``performed_by_id``: el
    # profesional ejecutor puede no tener usuario, y quien la aplica —una enfermera, por
    # ejemplo— puede no estar en el padrón de profesionales.
    performed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_hosp_practices_performed_by_user_id_users",
        ),
        index=True,
    )
    performed_by_user_name: Mapped[str | None] = mapped_column(String(150))
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
    # Lo que dijo la cartilla del plan cuando se registró la práctica. Queda acá porque la
    # cartilla se edita y la internación no puede cambiar de condiciones a posteriori.
    authorization_number: Mapped[str | None] = mapped_column(String(100))
    copayment_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal(0), server_default="0"
    )
    copayment_charge_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "charge_items.id",
            ondelete="SET NULL",
            # El nombre que genera la convención pasa los 63 caracteres de PostgreSQL.
            name="fk_hosp_practices_copayment_charge_item_id_charge_items",
        ),
        unique=True,
    )
    # Por qué se registró una práctica que la cartilla no cubre.
    coverage_override_reason: Mapped[str | None] = mapped_column(Text)
    prescribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indication: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    practice: Mapped[MedicalPractice] = relationship()
    charge_item: Mapped[ChargeItem | None] = relationship(
        foreign_keys=[charge_item_id],
    )
    copayment_charge_item: Mapped[ChargeItem | None] = relationship(
        foreign_keys=[copayment_charge_item_id],
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("copayment_amount >= 0", name="non_negative_copayment"),
        Index(
            "ix_hospitalization_practices_hospitalization_prescribed",
            "hospitalization_id",
            "prescribed_at",
        ),
    )
