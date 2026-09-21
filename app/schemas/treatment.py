"""Schemas de la medicación, el tratamiento y las notas de la internación."""

import uuid
from datetime import datetime, time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.treatment import (
    AdministrationStatus,
    ClinicalNoteKind,
    ClinicalNoteStatus,
    MedicationRoute,
    ScheduleKind,
    TreatmentKind,
    TreatmentStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TreatmentCreate(BaseModel):
    """Lo que se le empieza a dar al paciente."""

    kind: TreatmentKind = TreatmentKind.MEDICATION
    description: str = Field(min_length=1, max_length=250)
    presentation: str | None = Field(default=None, max_length=150)
    dose: str | None = Field(default=None, max_length=100)
    route: MedicationRoute | None = None
    frequency: str | None = Field(default=None, max_length=100)
    started_at: datetime | None = None
    prescribed_by_id: uuid.UUID | None = None
    indication: str | None = None
    #: Cómo se reparte en el tiempo: es lo que deja calcular la próxima toma.
    schedule_kind: ScheduleKind = ScheduleKind.AS_NEEDED
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    times_of_day: list[time] | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def _schedule_is_complete(self):
        """Un esquema a medio cargar no genera horarios: mejor rechazarlo que
        mostrar una indicación que nunca se vence."""

        if self.schedule_kind == ScheduleKind.INTERVAL and not self.interval_hours:
            raise ValueError("El esquema por intervalo necesita cada cuántas horas se da")
        if self.schedule_kind == ScheduleKind.TIMES and not self.times_of_day:
            raise ValueError("El esquema por horarios necesita al menos un horario")
        return self



class TreatmentUpdate(BaseModel):
    """Se corrige la indicación en curso: dosis, vía, frecuencia o quién la indicó."""

    description: str = Field(min_length=1, max_length=250)
    presentation: str | None = Field(default=None, max_length=150)
    dose: str | None = Field(default=None, max_length=100)
    route: MedicationRoute | None = None
    frequency: str | None = Field(default=None, max_length=100)
    prescribed_by_id: uuid.UUID | None = None
    indication: str | None = None
    #: Cómo se reparte en el tiempo: es lo que deja calcular la próxima toma.
    schedule_kind: ScheduleKind = ScheduleKind.AS_NEEDED
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    times_of_day: list[time] | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def _schedule_is_complete(self):
        """Un esquema a medio cargar no genera horarios: mejor rechazarlo que
        mostrar una indicación que nunca se vence."""

        if self.schedule_kind == ScheduleKind.INTERVAL and not self.interval_hours:
            raise ValueError("El esquema por intervalo necesita cada cuántas horas se da")
        if self.schedule_kind == ScheduleKind.TIMES and not self.times_of_day:
            raise ValueError("El esquema por horarios necesita al menos un horario")
        return self


class TreatmentStopCreate(BaseModel):
    """Cortar una indicación: suspendida antes de tiempo o cumplida."""

    status: TreatmentStatus = TreatmentStatus.SUSPENDED
    ended_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class TreatmentRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    kind: TreatmentKind
    description: str
    presentation: str | None
    dose: str | None
    route: MedicationRoute | None
    frequency: str | None
    schedule_kind: ScheduleKind
    interval_hours: int | None
    times_of_day: list[time] | None
    status: TreatmentStatus
    started_at: datetime
    ended_at: datetime | None
    end_reason: str | None
    prescribed_by_id: uuid.UUID | None
    recorded_by_user_id: uuid.UUID | None
    recorded_by_user_name: str | None
    indication: str | None
    created_at: datetime


class ClinicalNoteCreate(BaseModel):
    """Una evolución, una observación o la atención de otro médico."""

    kind: ClinicalNoteKind = ClinicalNoteKind.EVOLUTION
    note: str = Field(min_length=1)
    author_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    noted_at: datetime | None = None


class ClinicalNoteVoidCreate(BaseModel):
    """Una nota cargada por error se anula con su motivo; no se borra."""

    reason: str | None = Field(default=None, max_length=500)
    actor: str | None = Field(default=None, max_length=150)


class ClinicalNoteRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    kind: ClinicalNoteKind
    status: ClinicalNoteStatus
    note: str
    author_id: uuid.UUID | None
    service_id: uuid.UUID | None
    recorded_by_user_id: uuid.UUID | None
    recorded_by_user_name: str | None
    noted_at: datetime
    voided_at: datetime | None
    voided_by: str | None
    void_reason: str | None
    created_at: datetime


class AdministrationCreate(BaseModel):
    """Una toma: lo que se le dio al paciente, o lo que no se le pudo dar."""

    status: AdministrationStatus = AdministrationStatus.GIVEN
    administered_at: datetime | None = None
    #: Vacía toma la dosis de la indicación: lo habitual es dar lo indicado.
    dose: str | None = Field(default=None, max_length=100)
    omission_reason: str | None = Field(default=None, max_length=500)
    administered_by_id: uuid.UUID | None = None
    notes: str | None = None


class AdministrationVoidCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    actor: str | None = Field(default=None, max_length=150)


class AdministrationRead(ORMModel):
    id: uuid.UUID
    treatment_id: uuid.UUID
    hospitalization_id: uuid.UUID
    status: AdministrationStatus
    administered_at: datetime
    dose: str | None
    route: MedicationRoute | None
    omission_reason: str | None
    administered_by_id: uuid.UUID | None
    recorded_by_user_id: uuid.UUID | None
    recorded_by_user_name: str | None
    notes: str | None
    voided_at: datetime | None
    voided_by: str | None
    void_reason: str | None
    created_at: datetime


class DoseState(str, Enum):
    GIVEN = "GIVEN"
    OMITTED = "OMITTED"
    PENDING = "PENDING"
    OVERDUE = "OVERDUE"


class MedicationRoundRead(BaseModel):
    """Una indicación activa vista desde el pasillo: a quién, qué y cuándo fue la última."""

    treatment_id: uuid.UUID
    hospitalization_id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    ward: str | None
    room_code: str | None
    bed_code: str | None
    service_id: uuid.UUID | None
    service_name: str | None
    kind: TreatmentKind
    description: str
    presentation: str | None
    dose: str | None
    route: MedicationRoute | None
    frequency: str | None
    schedule_kind: ScheduleKind
    interval_hours: int | None
    times_of_day: list[time] | None
    started_at: datetime
    last_administered_at: datetime | None
    #: Cuántas tomas se registraron desde que empezó la indicación.
    administrations: int
    #: El horario que sigue sin dar, y si ya se pasó de hora.
    next_due_at: datetime | None
    overdue: bool
    #: La línea de tiempo de la ventana pedida: lo que se dio y lo que falta.
    slots: list["DoseSlotRead"]


class DoseSlotRead(BaseModel):
    due_at: datetime
    state: DoseState
    administration_id: uuid.UUID | None
    dose: str | None
    reason: str | None


MedicationRoundRead.model_rebuild()
