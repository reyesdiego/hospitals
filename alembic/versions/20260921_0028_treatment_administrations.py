"""registro de administración de enfermería"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260921_0028"
down_revision = "20260921_0027"
branch_labels = None
depends_on = None

STATUSES = ("GIVEN", "OMITTED", "VOID")


def upgrade():
    bind = op.get_bind()
    status = postgresql.ENUM(*STATUSES, name="administration_status", create_type=False)
    status.create(bind, checkfirst=True)
    op.execute(
        "ALTER TYPE hospitalization_event_type ADD VALUE IF NOT EXISTS 'TREATMENT_ADMINISTERED'"
    )
    route = postgresql.ENUM(name="medication_route", create_type=False)

    op.create_table(
        "treatment_administrations",
        sa.Column("treatment_id", sa.Uuid(), nullable=False),
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("status", status, server_default="GIVEN", nullable=False),
        sa.Column("administered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dose", sa.String(length=100), nullable=True),
        sa.Column("route", route, nullable=True),
        sa.Column("omission_reason", sa.String(length=500), nullable=True),
        sa.Column("administered_by_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_name", sa.String(length=150), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.String(length=150), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["treatment_id"],
            ["hospitalization_treatments.id"],
            name="fk_treatment_administrations_treatment_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name="fk_treatment_administrations_hospitalization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["administered_by_id"],
            ["professionals.id"],
            name="fk_treatment_administrations_administered_by_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name="fk_treatment_administrations_recorded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_treatment_administrations")),
    )
    op.create_index(
        op.f("ix_treatment_administrations_treatment_id"),
        "treatment_administrations",
        ["treatment_id"],
    )
    op.create_index(
        op.f("ix_treatment_administrations_hospitalization_id"),
        "treatment_administrations",
        ["hospitalization_id"],
    )
    op.create_index(
        op.f("ix_treatment_administrations_administered_by_id"),
        "treatment_administrations",
        ["administered_by_id"],
    )
    op.create_index(
        op.f("ix_treatment_administrations_recorded_by_user_id"),
        "treatment_administrations",
        ["recorded_by_user_id"],
    )
    op.create_index(
        "ix_treatment_administrations_stay_moment",
        "treatment_administrations",
        ["hospitalization_id", "administered_at"],
    )


def downgrade():
    op.drop_table("treatment_administrations")
    postgresql.ENUM(name="administration_status").drop(op.get_bind(), checkfirst=True)
