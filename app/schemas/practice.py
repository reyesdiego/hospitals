"""Schemas of the medical practice catalog (nomenclador) and its tariffs."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.practice import (
    Nomenclador,
    PlanCoverageStatus,
    PracticeChapter,
    PracticeOrderStatus,
    PracticeSetting,
    PracticeType,
)
from app.schemas.workflow import ChargeItemRead


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MedicalPracticeCreate(BaseModel):
    nomenclador: Nomenclador = Nomenclador.NACIONAL
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=250)
    description: str | None = None
    chapter: PracticeChapter
    practice_type: PracticeType
    setting: PracticeSetting = PracticeSetting.AMBOS
    galeno_units: Decimal = Field(default=Decimal(0), ge=0, max_digits=10, decimal_places=2)
    expense_units: Decimal = Field(default=Decimal(0), ge=0, max_digits=10, decimal_places=2)
    anesthesia_units: Decimal = Field(default=Decimal(0), ge=0, max_digits=10, decimal_places=2)
    biochemical_units: Decimal = Field(default=Decimal(0), ge=0, max_digits=10, decimal_places=2)
    radiology_units: Decimal = Field(default=Decimal(0), ge=0, max_digits=10, decimal_places=2)
    requires_authorization: bool = False
    requires_consent: bool = False
    # Carencia con la que la práctica entra en cualquier plan, salvo que el plan pacte otra.
    default_waiting_period_days: int = Field(default=0, ge=0, le=3650)
    is_active: bool = True
    valid_from: date | None = None
    valid_until: date | None = None
    notes: str | None = None


class MedicalPracticeUpdate(MedicalPracticeCreate):
    pass


class MedicalPracticeRead(ORMModel):
    id: uuid.UUID
    nomenclador: Nomenclador
    code: str
    name: str
    description: str | None
    chapter: PracticeChapter
    practice_type: PracticeType
    setting: PracticeSetting
    galeno_units: Decimal
    expense_units: Decimal
    anesthesia_units: Decimal
    biochemical_units: Decimal
    radiology_units: Decimal
    requires_authorization: bool
    requires_consent: bool
    default_waiting_period_days: int
    is_active: bool
    valid_from: date | None
    valid_until: date | None
    notes: str | None
    created_at: datetime


class HealthPlanPracticeCreate(BaseModel):
    """Cobertura de una práctica dentro de un plan.

    ``waiting_period_days`` vacío significa que el plan no pactó carencia propia y rige la
    de la práctica.
    """

    practice_id: uuid.UUID
    is_covered: bool = True
    waiting_period_days: int | None = Field(default=None, ge=0, le=3650)
    copayment_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    requires_authorization: bool = False
    notes: str | None = None


class HealthPlanPracticeUpdate(BaseModel):
    """``waiting_period_days`` vacío devuelve la práctica a la carencia del nomenclador."""

    is_covered: bool = True
    waiting_period_days: int | None = Field(default=None, ge=0, le=3650)
    copayment_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    requires_authorization: bool = False
    notes: str | None = None


class HealthPlanPracticeBulkCreate(BaseModel):
    """Alta de varias prácticas con las mismas condiciones, para armar la cartilla de un
    capítulo entero sin cargarlo práctica por práctica."""

    practice_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    is_covered: bool = True
    waiting_period_days: int | None = Field(default=None, ge=0, le=3650)
    copayment_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    requires_authorization: bool = False
    notes: str | None = None


class HealthPlanPracticeRead(ORMModel):
    id: uuid.UUID
    health_plan_id: uuid.UUID
    practice_id: uuid.UUID
    # Datos de la práctica, para que la cartilla se lea sin pedir el catálogo entero.
    practice_code: str
    practice_name: str
    nomenclador: Nomenclador
    chapter: PracticeChapter
    practice_type: PracticeType
    practice_requires_authorization: bool
    # Carencia del nomenclador, la que pactó el plan (vacía si no pactó) y la que rige.
    practice_waiting_period_days: int
    is_covered: bool
    waiting_period_days: int | None
    effective_waiting_period_days: int
    copayment_amount: Decimal
    requires_authorization: bool
    notes: str | None
    created_at: datetime


class HealthPlanPracticeBulkRead(BaseModel):
    """Resultado del alta masiva: lo que se agregó y lo que ya estaba en la cartilla."""

    created: list[HealthPlanPracticeRead]
    skipped_practice_ids: list[uuid.UUID]


class MedicalPracticeTariffCreate(BaseModel):
    """``payer_id`` empty means the institutional tariff (private patient).

    ``professional_fee``/``expense_amount`` may be left empty when ``unit_value`` is
    informed: they are then derived from the units of the practice.
    """

    payer_id: uuid.UUID | None = None
    health_plan_id: uuid.UUID | None = None
    unit_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    professional_fee: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    expense_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    coinsurance: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="ARS", min_length=3, max_length=3)
    valid_from: date
    valid_until: date | None = None
    notes: str | None = None


class MedicalPracticeTariffUpdate(MedicalPracticeTariffCreate):
    pass


class MedicalPracticeTariffRead(ORMModel):
    id: uuid.UUID
    practice_id: uuid.UUID
    payer_id: uuid.UUID | None
    health_plan_id: uuid.UUID | None
    unit_value: Decimal | None
    professional_fee: Decimal
    expense_amount: Decimal
    total_amount: Decimal
    coinsurance: Decimal
    currency: str
    valid_from: date
    valid_until: date | None
    notes: str | None
    created_at: datetime


class HospitalizationPracticeCreate(BaseModel):
    """A practice indicated in a hospitalization.

    ``prescribed_by_id`` is the professional who indicated it. Informing ``performed_at``
    registers the practice as already performed, which is what generates the charge;
    ``unit_price`` overrides the tariff when the practice has no agreed value.
    """

    practice_id: uuid.UUID
    prescribed_by_id: uuid.UUID
    performed_by_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=12, decimal_places=3)
    prescribed_at: datetime | None = None
    performed_at: datetime | None = None
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    indication: str | None = None
    notes: str | None = None
    recorded_by: str | None = Field(default=None, max_length=150)
    # Número que dio el financiador, cuando la cartilla del plan exige autorización.
    authorization_number: str | None = Field(default=None, max_length=100)
    # La cartilla se puede saltear, pero no en silencio: el motivo queda en la práctica y
    # en el evento de auditoría de la internación.
    override_coverage_rules: bool = False
    override_reason: str | None = Field(default=None, max_length=500)


class HospitalizationPracticePerformCreate(BaseModel):
    performed_at: datetime | None = None
    performed_by_id: uuid.UUID | None = None
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    recorded_by: str | None = Field(default=None, max_length=150)
    notes: str | None = None
    authorization_number: str | None = Field(default=None, max_length=100)
    override_coverage_rules: bool = False
    override_reason: str | None = Field(default=None, max_length=500)


class HospitalizationPracticeCancelCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    actor: str | None = Field(default=None, max_length=150)


class HospitalizationPracticeRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    practice_id: uuid.UUID
    practice_code: str
    practice_name: str
    prescribed_by_id: uuid.UUID
    performed_by_id: uuid.UUID | None
    service_id: uuid.UUID | None
    charge_item_id: uuid.UUID | None
    status: PracticeOrderStatus
    quantity: Decimal
    prescribed_at: datetime
    performed_at: datetime | None
    cancelled_at: datetime | None
    indication: str | None
    notes: str | None
    authorization_number: str | None
    copayment_amount: Decimal
    copayment_charge_item_id: uuid.UUID | None
    coverage_override_reason: str | None
    created_at: datetime
    charge: ChargeItemRead | None = None


class PlanCoverageCheckRead(BaseModel):
    """Lo que la cartilla del plan dice sobre una práctica antes de indicarla."""

    status: PlanCoverageStatus
    blocked: bool
    copayment_amount: Decimal
    requires_authorization: bool
    waiting_period_days: int
    available_from: date | None
    health_plan_id: uuid.UUID | None
    message: str | None
