"""Esquemas de las recetas e indicaciones del alta."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.prescription import PrescriptionKind


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DischargePrescriptionCreate(BaseModel):
    """Un renglón de la receta o de las indicaciones.

    ``practice_id`` solo tiene sentido en las indicaciones de prácticas: trae el nombre del
    nomenclador. La medicación va como texto, porque el vademécum no vive en este sistema.
    """

    kind: PrescriptionKind
    practice_id: uuid.UUID | None = None
    description: str = Field(default="", max_length=250)
    presentation: str | None = Field(default=None, max_length=150)
    dosage: str | None = Field(default=None, max_length=250)
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=10, decimal_places=2)
    duration_days: int | None = Field(default=None, gt=0, le=3650)
    instructions: str | None = None
    prescribed_by_id: uuid.UUID | None = None


class DischargePrescriptionUpdate(DischargePrescriptionCreate):
    pass


class DischargePrescriptionRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    kind: PrescriptionKind
    practice_id: uuid.UUID | None
    description: str
    presentation: str | None
    dosage: str | None
    quantity: Decimal
    duration_days: int | None
    instructions: str | None
    prescribed_by_id: uuid.UUID | None
    prescribed_by_user_name: str | None
    prescribed_at: datetime
    created_at: datetime
