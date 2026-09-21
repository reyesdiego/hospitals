"""Catálogo CIE-10 de diagnósticos y los que se le asientan a una internación.

La clasificación es un árbol: capítulo → grupo → categoría (3 caracteres) → subcategoría
(4 o más). Los capítulos y los grupos ordenan la lista pero no son diagnósticos: lo que se
le asienta a un paciente es una categoría o una subcategoría, que es lo que pide cualquier
informe estadístico y lo que acepta un financiador.

Las filas se cargan del CSV de ``app/db/seeds/cie10.csv``; la tabla es editable porque una
institución agrega códigos propios y da de baja los que dejó de usar.

:class:`HospitalizationDiagnosis` es el diagnóstico de un paciente: el de ingreso, que es
presuntivo y se carga en la admisión, y el de egreso, que es el que firma el médico con el
alta. Son dos momentos distintos y conviven, porque la diferencia entre lo que se sospechó
y lo que resultó es parte de la historia.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class DiagnosisLevel(str, enum.Enum):
    CHAPTER = "CHAPTER"  # A00-B99
    BLOCK = "BLOCK"  # A00-A09
    CATEGORY = "CATEGORY"  # A00
    SUBCATEGORY = "SUBCATEGORY"  # A000


#: Los niveles que se pueden asentar como diagnóstico; el resto solo agrupa.
CODIFIABLE_LEVELS = {DiagnosisLevel.CATEGORY, DiagnosisLevel.SUBCATEGORY}


class DiagnosisCode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "diagnosis_codes"

    code: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(300))
    level: Mapped[DiagnosisLevel] = mapped_column(Enum(DiagnosisLevel, name="diagnosis_level"))
    # El padre en el árbol y el capítulo al que pertenece. Se guardan por código y no por
    # id porque el código es la identidad del diagnóstico en cualquier otro sistema.
    parent_code: Mapped[str | None] = mapped_column(
        ForeignKey("diagnosis_codes.code", ondelete="RESTRICT"), index=True
    )
    chapter_code: Mapped[str | None] = mapped_column(String(10), index=True)
    #: Un código que se deja de usar se desactiva; borrarlo dejaría historias sin diagnóstico.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # Restricción y no índice único: ``parent_code`` la referencia, y la tabla se crea
        # de una sola vez.
        UniqueConstraint("code", name="uq_diagnosis_codes_code"),
        # La búsqueda del mostrador es por descripción: se lista por código dentro del nivel.
        Index("ix_diagnosis_codes_level_code", "level", "code"),
    )


class DiagnosisRole(str, enum.Enum):
    """Qué lugar ocupa el diagnóstico en la internación."""

    #: El que motivó la internación. Uno solo por momento.
    PRINCIPAL = "PRINCIPAL"
    SECONDARY = "SECONDARY"
    #: Lo que el paciente ya traía y condiciona el tratamiento.
    COMORBIDITY = "COMORBIDITY"
    #: Lo que apareció durante la internación.
    COMPLICATION = "COMPLICATION"


class DiagnosisStage(str, enum.Enum):
    ADMISSION = "ADMISSION"  # de ingreso, presuntivo
    DISCHARGE = "DISCHARGE"  # de egreso, el que firma el alta médica


class HospitalizationDiagnosis(UUIDMixin, TimestampMixin, Base):
    """Un diagnóstico asentado en una internación, con el código del catálogo congelado.

    El código y el texto se copian del catálogo: la clasificación se edita y la historia
    clínica tiene que seguir leyéndose igual dentro de diez años.
    """

    __tablename__ = "hospitalization_diagnoses"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "hospitalizations.id",
            ondelete="RESTRICT",
            # El nombre que genera la convención pasa los 63 caracteres de PostgreSQL.
            name="fk_hosp_diagnoses_hospitalization_id",
        ),
        index=True,
    )
    diagnosis_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "diagnosis_codes.id",
            ondelete="RESTRICT",
            name="fk_hosp_diagnoses_diagnosis_code_id",
        ),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(300))
    role: Mapped[DiagnosisRole] = mapped_column(
        Enum(DiagnosisRole, name="diagnosis_role"),
        default=DiagnosisRole.SECONDARY,
        server_default=DiagnosisRole.SECONDARY.value,
    )
    stage: Mapped[DiagnosisStage] = mapped_column(
        Enum(DiagnosisStage, name="diagnosis_stage"),
        default=DiagnosisStage.ADMISSION,
        server_default=DiagnosisStage.ADMISSION.value,
    )
    #: El profesional que lo diagnosticó; puede no tener usuario en el sistema.
    diagnosed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "professionals.id",
            ondelete="RESTRICT",
            name="fk_hosp_diagnoses_diagnosed_by_id",
        ),
        index=True,
    )
    #: Quién lo cargó en el sistema, que no siempre es quien diagnosticó.
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_hosp_diagnoses_recorded_by_user_id"),
        index=True,
    )
    recorded_by_user_name: Mapped[str | None] = mapped_column(String(150))
    diagnosed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    diagnosis_code: Mapped[DiagnosisCode] = relationship()

    __table_args__ = (
        # El mismo código no se asienta dos veces en el mismo momento de la internación.
        UniqueConstraint(
            "hospitalization_id",
            "diagnosis_code_id",
            "stage",
            name="uq_hosp_diagnoses_hospitalization_code_stage",
        ),
        # Un solo diagnóstico principal por momento: es el que va a la estadística.
        Index(
            "uq_principal_diagnosis_per_stage",
            "hospitalization_id",
            "stage",
            unique=True,
            postgresql_where=text("role = 'PRINCIPAL'"),
        ),
    )
