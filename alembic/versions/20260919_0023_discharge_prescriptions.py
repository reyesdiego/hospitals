"""recetas e indicaciones del alta"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260919_0023"
down_revision = "20260919_0022"
branch_labels = None
depends_on = None

KINDS = ("MEDICATION", "PRACTICE")


def upgrade():
    bind = op.get_bind()
    kind = postgresql.ENUM(*KINDS, name="prescription_kind", create_type=False)
    kind.create(bind, checkfirst=True)

    op.create_table(
        "discharge_prescriptions",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", kind, nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(length=250), nullable=False),
        sa.Column("presentation", sa.String(length=150), nullable=True),
        sa.Column("dosage", sa.String(length=250), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), server_default="1", nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("prescribed_by_id", sa.Uuid(), nullable=True),
        sa.Column("prescribed_by_user_name", sa.String(length=150), nullable=True),
        sa.Column("prescribed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_discharge_prescriptions_positive_quantity")),
        sa.CheckConstraint(
            "duration_days IS NULL OR duration_days > 0",
            name=op.f("ck_discharge_prescriptions_positive_duration"),
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_discharge_prescriptions_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["medical_practices.id"],
            name=op.f("fk_discharge_prescriptions_practice_id_medical_practices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prescribed_by_id"],
            ["professionals.id"],
            name=op.f("fk_discharge_prescriptions_prescribed_by_id_professionals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discharge_prescriptions")),
    )
    op.create_index(
        op.f("ix_discharge_prescriptions_hospitalization_id"),
        "discharge_prescriptions",
        ["hospitalization_id"],
    )
    op.create_index(
        op.f("ix_discharge_prescriptions_practice_id"), "discharge_prescriptions", ["practice_id"]
    )
    op.create_index(
        op.f("ix_discharge_prescriptions_prescribed_by_id"),
        "discharge_prescriptions",
        ["prescribed_by_id"],
    )
    op.create_index(
        "ix_discharge_prescriptions_hospitalization_kind",
        "discharge_prescriptions",
        ["hospitalization_id", "kind"],
    )


def downgrade():
    op.drop_table("discharge_prescriptions")
    postgresql.ENUM(name="prescription_kind").drop(op.get_bind(), checkfirst=True)
