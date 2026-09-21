"""diagnósticos de la internación"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260920_0026"
down_revision = "20260920_0025"
branch_labels = None
depends_on = None

ROLES = ("PRINCIPAL", "SECONDARY", "COMORBIDITY", "COMPLICATION")
STAGES = ("ADMISSION", "DISCHARGE")
NEW_EVENTS = ("DIAGNOSIS_RECORDED", "DIAGNOSIS_REMOVED")


def upgrade():
    bind = op.get_bind()
    role = postgresql.ENUM(*ROLES, name="diagnosis_role", create_type=False)
    role.create(bind, checkfirst=True)
    stage = postgresql.ENUM(*STAGES, name="diagnosis_stage", create_type=False)
    stage.create(bind, checkfirst=True)
    for event in NEW_EVENTS:
        op.execute(
            f"ALTER TYPE hospitalization_event_type ADD VALUE IF NOT EXISTS '{event}'"
        )

    op.create_table(
        "hospitalization_diagnoses",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("diagnosis_code_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("role", role, server_default="SECONDARY", nullable=False),
        sa.Column("stage", stage, server_default="ADMISSION", nullable=False),
        sa.Column("diagnosed_by_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_name", sa.String(length=150), nullable=True),
        sa.Column("diagnosed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name="fk_hosp_diagnoses_hospitalization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["diagnosis_code_id"],
            ["diagnosis_codes.id"],
            name="fk_hosp_diagnoses_diagnosis_code_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["diagnosed_by_id"],
            ["professionals.id"],
            name="fk_hosp_diagnoses_diagnosed_by_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name="fk_hosp_diagnoses_recorded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospitalization_diagnoses")),
        sa.UniqueConstraint(
            "hospitalization_id",
            "diagnosis_code_id",
            "stage",
            name="uq_hosp_diagnoses_hospitalization_code_stage",
        ),
    )
    op.create_index(
        op.f("ix_hospitalization_diagnoses_hospitalization_id"),
        "hospitalization_diagnoses",
        ["hospitalization_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_diagnoses_diagnosis_code_id"),
        "hospitalization_diagnoses",
        ["diagnosis_code_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_diagnoses_diagnosed_by_id"),
        "hospitalization_diagnoses",
        ["diagnosed_by_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_diagnoses_recorded_by_user_id"),
        "hospitalization_diagnoses",
        ["recorded_by_user_id"],
    )
    # Un solo diagnóstico principal por momento de la internación.
    op.create_index(
        "uq_principal_diagnosis_per_stage",
        "hospitalization_diagnoses",
        ["hospitalization_id", "stage"],
        unique=True,
        postgresql_where=sa.text("role = 'PRINCIPAL'"),
    )


def downgrade():
    op.drop_table("hospitalization_diagnoses")
    bind = op.get_bind()
    postgresql.ENUM(name="diagnosis_stage").drop(bind, checkfirst=True)
    postgresql.ENUM(name="diagnosis_role").drop(bind, checkfirst=True)
