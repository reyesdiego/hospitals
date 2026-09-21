"""Lo que se le hace al paciente mientras está internado, además de las prácticas.

Dos cosas distintas que hasta ahora no tenían dónde anotarse:

* la **medicación y el tratamiento en curso** —qué recibe, en qué dosis, por qué vía y
  cada cuánto—, que es un plan que empieza, se suspende y se termina, y no un cargo
  puntual como una práctica;
* las **evoluciones, observaciones e interconsultas**, que es lo que escribe el médico de
  cabecera cada día y lo que deja anotado el de otra especialidad cuando pasa a ver al
  paciente;
* el **registro de administración**: cada toma que enfermería efectivamente le da al
  paciente, o que no le pudo dar y por qué. La indicación dice lo que hay que hacer; esto
  dice lo que pasó, y son dos cosas distintas.

Ninguna de las dos se borra: una indicación que se deja de dar se suspende y una nota
cargada por error se anula con su motivo. La historia clínica se corrige agregando, no
haciendo desaparecer.
"""

import enum
import uuid
from datetime import datetime, time

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class MedicationRoute(str, enum.Enum):
    ORAL = "ORAL"
    INTRAVENOUS = "INTRAVENOUS"
    INTRAMUSCULAR = "INTRAMUSCULAR"
    SUBCUTANEOUS = "SUBCUTANEOUS"
    INHALATORY = "INHALATORY"
    TOPICAL = "TOPICAL"
    RECTAL = "RECTAL"
    OTHER = "OTHER"


class TreatmentKind(str, enum.Enum):
    MEDICATION = "MEDICATION"  # un fármaco con su dosis
    TREATMENT = "TREATMENT"  # kinesiología, oxígeno, dieta, curaciones


class ScheduleKind(str, enum.Enum):
    """Cómo se reparte en el tiempo lo que hay que dar.

    Es lo que permite calcular la próxima toma y saber cuál se pasó de hora. Sin esto la
    frecuencia es una frase que el sistema no puede leer.
    """

    #: Cada N horas, contadas desde la última toma: "cada 8 horas".
    INTERVAL = "INTERVAL"
    #: Horarios fijos del día: 08:00, 14:00 y 20:00.
    TIMES = "TIMES"
    #: Una sola vez.
    ONCE = "ONCE"
    #: A demanda: se da si el paciente lo necesita, no hay horario que se venza.
    AS_NEEDED = "AS_NEEDED"
    #: Continuo: un goteo o el oxígeno no se dan por tomas.
    CONTINUOUS = "CONTINUOUS"


#: Los esquemas que generan horarios; el resto no puede vencerse.
SCHEDULED_KINDS = {ScheduleKind.INTERVAL, ScheduleKind.TIMES, ScheduleKind.ONCE}


class TreatmentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"  # se cortó antes de tiempo
    COMPLETED = "COMPLETED"  # cumplió el plan indicado


class HospitalizationTreatment(UUIDMixin, TimestampMixin, Base):
    """Una indicación en curso: medicación o tratamiento, con su dosis y frecuencia."""

    __tablename__ = "hospitalization_treatments"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "hospitalizations.id",
            ondelete="RESTRICT",
            # El nombre que genera la convención pasa los 63 caracteres de PostgreSQL.
            name="fk_hosp_treatments_hospitalization_id",
        ),
        index=True,
    )
    kind: Mapped[TreatmentKind] = mapped_column(
        Enum(TreatmentKind, name="treatment_kind"),
        default=TreatmentKind.MEDICATION,
        server_default=TreatmentKind.MEDICATION.value,
    )
    # El vademécum no es parte de este sistema: la droga es texto, como en las recetas.
    description: Mapped[str] = mapped_column(String(250))
    presentation: Mapped[str | None] = mapped_column(String(150))
    dose: Mapped[str | None] = mapped_column(String(100))
    route: Mapped[MedicationRoute | None] = mapped_column(
        Enum(MedicationRoute, name="medication_route")
    )
    #: Cómo se lee la frecuencia en el papel. Se completa sola desde el esquema cuando
    #: no se escribe.
    frequency: Mapped[str | None] = mapped_column(String(100))
    schedule_kind: Mapped[ScheduleKind] = mapped_column(
        Enum(ScheduleKind, name="schedule_kind"),
        default=ScheduleKind.AS_NEEDED,
        server_default=ScheduleKind.AS_NEEDED.value,
    )
    #: Cada cuántas horas, para el esquema por intervalo.
    interval_hours: Mapped[int | None] = mapped_column(Integer)
    #: Horarios fijos del día, para el esquema por horarios.
    times_of_day: Mapped[list[time] | None] = mapped_column(ARRAY(Time))
    status: Mapped[TreatmentStatus] = mapped_column(
        Enum(TreatmentStatus, name="treatment_status"),
        default=TreatmentStatus.ACTIVE,
        server_default=TreatmentStatus.ACTIVE.value,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Por qué se cortó: lo que explica una suspensión es tan importante como la indicación.
    end_reason: Mapped[str | None] = mapped_column(String(500))
    prescribed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "professionals.id",
            ondelete="RESTRICT",
            name="fk_hosp_treatments_prescribed_by_id",
        ),
        index=True,
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_hosp_treatments_recorded_by_user_id"),
        index=True,
    )
    recorded_by_user_name: Mapped[str | None] = mapped_column(String(150))
    indication: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "ix_hospitalization_treatments_stay_status",
            "hospitalization_id",
            "status",
        ),
    )


class ClinicalNoteKind(str, enum.Enum):
    EVOLUTION = "EVOLUTION"  # la evolución diaria del médico de cabecera
    OBSERVATION = "OBSERVATION"  # una observación suelta sobre el paciente
    INTERCONSULTATION = "INTERCONSULTATION"  # pasó a verlo un médico de otra especialidad
    NURSING = "NURSING"  # lo que deja anotado enfermería


class ClinicalNoteStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    VOID = "VOID"


class HospitalizationNote(UUIDMixin, TimestampMixin, Base):
    """Una nota en la historia de la internación: evolución, observación o interconsulta.

    Queda quién la escribió —el profesional, que puede ser de otro servicio— y quién la
    cargó, que no siempre es la misma persona.
    """

    __tablename__ = "hospitalization_notes"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "hospitalizations.id",
            ondelete="RESTRICT",
            name="fk_hosp_notes_hospitalization_id",
        ),
        index=True,
    )
    kind: Mapped[ClinicalNoteKind] = mapped_column(
        Enum(ClinicalNoteKind, name="clinical_note_kind"),
        default=ClinicalNoteKind.EVOLUTION,
        server_default=ClinicalNoteKind.EVOLUTION.value,
    )
    status: Mapped[ClinicalNoteStatus] = mapped_column(
        Enum(ClinicalNoteStatus, name="clinical_note_status"),
        default=ClinicalNoteStatus.ACTIVE,
        server_default=ClinicalNoteStatus.ACTIVE.value,
    )
    note: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("professionals.id", ondelete="RESTRICT", name="fk_hosp_notes_author_id"),
        index=True,
    )
    #: El servicio desde el que se hizo la interconsulta.
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT", name="fk_hosp_notes_service_id"),
        index=True,
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_hosp_notes_recorded_by_user_id"),
        index=True,
    )
    recorded_by_user_name: Mapped[str | None] = mapped_column(String(150))
    noted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[str | None] = mapped_column(String(150))
    void_reason: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index(
            "ix_hospitalization_notes_stay_noted",
            "hospitalization_id",
            "noted_at",
        ),
    )


class AdministrationStatus(str, enum.Enum):
    GIVEN = "GIVEN"
    #: No se pudo dar: el paciente estaba en ayunas, la rechazó, no estaba en la cama.
    OMITTED = "OMITTED"
    VOID = "VOID"  # cargada por error


class TreatmentAdministration(UUIDMixin, TimestampMixin, Base):
    """Una toma: lo que enfermería le dio al paciente, cuándo y quién lo hizo.

    Una toma cargada por error se anula con su motivo. Lo que se le dio a un paciente no
    se borra de la historia.
    """

    __tablename__ = "treatment_administrations"

    treatment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "hospitalization_treatments.id",
            ondelete="RESTRICT",
            name="fk_treatment_administrations_treatment_id",
        ),
        index=True,
    )
    #: Se copia de la indicación: una toma no cambia de internación, y así el panel de
    #: enfermería no necesita el join para filtrar por sala o por paciente.
    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "hospitalizations.id",
            ondelete="RESTRICT",
            name="fk_treatment_administrations_hospitalization_id",
        ),
        index=True,
    )
    status: Mapped[AdministrationStatus] = mapped_column(
        Enum(AdministrationStatus, name="administration_status"),
        default=AdministrationStatus.GIVEN,
        server_default=AdministrationStatus.GIVEN.value,
    )
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: Lo que realmente se dio, que puede no ser la dosis indicada.
    dose: Mapped[str | None] = mapped_column(String(100))
    route: Mapped[MedicationRoute | None] = mapped_column(
        Enum(MedicationRoute, name="medication_route")
    )
    #: Por qué no se dio. Una omisión sin motivo no le sirve a nadie.
    omission_reason: Mapped[str | None] = mapped_column(String(500))
    administered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "professionals.id",
            ondelete="RESTRICT",
            name="fk_treatment_administrations_administered_by_id",
        ),
        index=True,
    )
    #: Quién la cargó en el sistema: la enfermera que la aplicó puede no estar en el
    #: padrón de profesionales.
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_treatment_administrations_recorded_by_user_id",
        ),
        index=True,
    )
    recorded_by_user_name: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[str | None] = mapped_column(String(150))
    void_reason: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index(
            "ix_treatment_administrations_stay_moment",
            "hospitalization_id",
            "administered_at",
        ),
    )
