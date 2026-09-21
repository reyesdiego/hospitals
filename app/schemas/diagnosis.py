"""Schemas del catálogo CIE-10."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.diagnosis import (
    CODIFIABLE_LEVELS,
    DiagnosisLevel,
    DiagnosisRole,
    DiagnosisStage,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DiagnosisCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    description: str = Field(min_length=1, max_length=300)
    level: DiagnosisLevel = DiagnosisLevel.SUBCATEGORY
    #: Código del padre en el árbol; vacío solo para un capítulo.
    parent_code: str | None = Field(default=None, max_length=10)
    chapter_code: str | None = Field(default=None, max_length=10)
    is_active: bool = True
    notes: str | None = None


class DiagnosisCodeUpdate(BaseModel):
    """El código es la identidad del diagnóstico: no se edita, se da de baja."""

    description: str = Field(min_length=1, max_length=300)
    level: DiagnosisLevel = DiagnosisLevel.SUBCATEGORY
    parent_code: str | None = Field(default=None, max_length=10)
    chapter_code: str | None = Field(default=None, max_length=10)
    is_active: bool = True
    notes: str | None = None


class DiagnosisCodeRead(ORMModel):
    id: uuid.UUID
    code: str
    description: str
    level: DiagnosisLevel
    parent_code: str | None
    chapter_code: str | None
    is_active: bool
    notes: str | None
    created_at: datetime

    @computed_field
    @property
    def codifiable(self) -> bool:
        """Si se le puede asentar a un paciente: capítulos y grupos solo agrupan."""

        return self.level in CODIFIABLE_LEVELS


class HospitalizationDiagnosisCreate(BaseModel):
    """Un diagnóstico que se le asienta a la internación.

    Se informa el código del catálogo —el ``id`` es interno— porque es lo que el médico
    tiene a mano y lo que viaja en cualquier interconsulta.
    """

    code: str = Field(min_length=1, max_length=10)
    role: DiagnosisRole = DiagnosisRole.SECONDARY
    stage: DiagnosisStage = DiagnosisStage.ADMISSION
    diagnosed_by_id: uuid.UUID | None = None
    diagnosed_at: datetime | None = None
    notes: str | None = None


class HospitalizationDiagnosisUpdate(BaseModel):
    """El código no se corrige: se quita el diagnóstico y se asienta el que corresponde."""

    role: DiagnosisRole = DiagnosisRole.SECONDARY
    diagnosed_by_id: uuid.UUID | None = None
    notes: str | None = None


class HospitalizationDiagnosisRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    diagnosis_code_id: uuid.UUID
    code: str
    description: str
    role: DiagnosisRole
    stage: DiagnosisStage
    diagnosed_by_id: uuid.UUID | None
    recorded_by_user_id: uuid.UUID | None
    recorded_by_user_name: str | None
    diagnosed_at: datetime
    notes: str | None
    created_at: datetime
