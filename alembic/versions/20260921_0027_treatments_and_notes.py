"""medicación, tratamiento y notas de evolución de la internación"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260921_0027"
down_revision = "20260920_0026"
branch_labels = None
depends_on = None

ROUTES = (
    "ORAL",
    "INTRAVENOUS",
    "INTRAMUSCULAR",
    "SUBCUTANEOUS",
    "INHALATORY",
    "TOPICAL",
    "RECTAL",
    "OTHER",
)
TREATMENT_KINDS = ("MEDICATION", "TREATMENT")
TREATMENT_STATUSES = ("ACTIVE", "SUSPENDED", "COMPLETED")
NOTE_KINDS = ("EVOLUTION", "OBSERVATION", "INTERCONSULTATION", "NURSING")
NOTE_STATUSES = ("ACTIVE", "VOID")
NEW_EVENTS = (
    "TREATMENT_STARTED",
    "TREATMENT_STOPPED",
    "CLINICAL_NOTE_ADDED",
    "CLINICAL_NOTE_VOIDED",
)

TIMESTAMPS = (
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    ),
)


def upgrade():
    bind = op.get_bind()
    route = postgresql.ENUM(*ROUTES, name="medication_route", create_type=False)
    route.create(bind, checkfirst=True)
    kind = postgresql.ENUM(*TREATMENT_KINDS, name="treatment_kind", create_type=False)
    kind.create(bind, checkfirst=True)
    status = postgresql.ENUM(*TREATMENT_STATUSES, name="treatment_status", create_type=False)
    status.create(bind, checkfirst=True)
    note_kind = postgresql.ENUM(*NOTE_KINDS, name="clinical_note_kind", create_type=False)
    note_kind.create(bind, checkfirst=True)
    note_status = postgresql.ENUM(*NOTE_STATUSES, name="clinical_note_status", create_type=False)
    note_status.create(bind, checkfirst=True)
    for event in NEW_EVENTS:
        op.execute(
            f"ALTER TYPE hospitalization_event_type ADD VALUE IF NOT EXISTS '{event}'"
        )

    op.create_table(
        "hospitalization_treatments",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", kind, server_default="MEDICATION", nullable=False),
        sa.Column("description", sa.String(length=250), nullable=False),
        sa.Column("presentation", sa.String(length=150), nullable=True),
        sa.Column("dose", sa.String(length=100), nullable=True),
        sa.Column("route", route, nullable=True),
        sa.Column("frequency", sa.String(length=100), nullable=True),
        sa.Column("status", status, server_default="ACTIVE", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=500), nullable=True),
        sa.Column("prescribed_by_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_name", sa.String(length=150), nullable=True),
        sa.Column("indication", sa.Text(), nullable=True),
        *TIMESTAMPS,
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name="fk_hosp_treatments_hospitalization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prescribed_by_id"],
            ["professionals.id"],
            name="fk_hosp_treatments_prescribed_by_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name="fk_hosp_treatments_recorded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospitalization_treatments")),
    )
    op.create_index(
        op.f("ix_hospitalization_treatments_hospitalization_id"),
        "hospitalization_treatments",
        ["hospitalization_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_treatments_prescribed_by_id"),
        "hospitalization_treatments",
        ["prescribed_by_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_treatments_recorded_by_user_id"),
        "hospitalization_treatments",
        ["recorded_by_user_id"],
    )
    op.create_index(
        "ix_hospitalization_treatments_stay_status",
        "hospitalization_treatments",
        ["hospitalization_id", "status"],
    )

    op.create_table(
        "hospitalization_notes",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", note_kind, server_default="EVOLUTION", nullable=False),
        sa.Column("status", note_status, server_default="ACTIVE", nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_name", sa.String(length=150), nullable=True),
        sa.Column("noted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.String(length=150), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        *TIMESTAMPS,
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name="fk_hosp_notes_hospitalization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["professionals.id"],
            name="fk_hosp_notes_author_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_hosp_notes_service_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name="fk_hosp_notes_recorded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospitalization_notes")),
    )
    op.create_index(
        op.f("ix_hospitalization_notes_hospitalization_id"),
        "hospitalization_notes",
        ["hospitalization_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_notes_author_id"), "hospitalization_notes", ["author_id"]
    )
    op.create_index(
        op.f("ix_hospitalization_notes_service_id"), "hospitalization_notes", ["service_id"]
    )
    op.create_index(
        op.f("ix_hospitalization_notes_recorded_by_user_id"),
        "hospitalization_notes",
        ["recorded_by_user_id"],
    )
    op.create_index(
        "ix_hospitalization_notes_stay_noted",
        "hospitalization_notes",
        ["hospitalization_id", "noted_at"],
    )


def downgrade():
    op.drop_table("hospitalization_notes")
    op.drop_table("hospitalization_treatments")
    bind = op.get_bind()
    for name in (
        "clinical_note_status",
        "clinical_note_kind",
        "treatment_status",
        "treatment_kind",
        "medication_route",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
