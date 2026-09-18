"""Schemas of the medical practice catalog (nomenclador) and its tariffs."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.practice import (
    Nomenclador,
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
    is_active: bool
    valid_from: date | None
    valid_until: date | None
    notes: str | None
    created_at: datetime


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


class HospitalizationPracticePerformCreate(BaseModel):
    performed_at: datetime | None = None
    performed_by_id: uuid.UUID | None = None
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    recorded_by: str | None = Field(default=None, max_length=150)
    notes: str | None = None


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
    created_at: datetime
    charge: ChargeItemRead | None = None
