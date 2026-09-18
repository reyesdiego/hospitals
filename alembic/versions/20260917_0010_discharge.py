"""discharge planning and clinical discharge"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260917_0010"
down_revision = "20260917_0009"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    destination = postgresql.ENUM(
        "HOME",
        "OTHER_FACILITY",
        "HOME_CARE",
        "REHABILITATION",
        "OTHER",
        name="discharge_destination",
        create_type=False,
    )
    plan_status = postgresql.ENUM(
        "PLANNED",
        "CONFIRMED",
        "COMPLETED",
        "CANCELLED",
        name="discharge_plan_status",
        create_type=False,
    )
    discharge_type = postgresql.ENUM(
        "MEDICAL",
        "VOLUNTARY",
        "TRANSFER",
        "DECEASED",
        "ABSCONDED",
        "OTHER",
        name="discharge_type",
        create_type=False,
    )
    for enum_type in (destination, plan_status, discharge_type):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "discharge_plans",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("destination", destination, nullable=False),
        sa.Column("requires_transport", sa.Boolean(), nullable=False),
        sa.Column("requires_home_care", sa.Boolean(), nullable=False),
        sa.Column("status", plan_status, nullable=False),
        sa.Column("created_by", sa.String(length=150), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_discharge_plans_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discharge_plans")),
    )
    op.create_index(
        op.f("ix_discharge_plans_hospitalization_id"),
        "discharge_plans",
        ["hospitalization_id"],
    )
    op.create_index(
        "uq_active_discharge_plan_per_hospitalization",
        "discharge_plans",
        ["hospitalization_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PLANNED', 'CONFIRMED')"),
    )

    op.create_table(
        "discharges",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("discharge_type", discharge_type, nullable=False),
        sa.Column("discharge_reason", sa.String(length=500), nullable=True),
        sa.Column("destination", destination, nullable=True),
        sa.Column("ordered_by", sa.String(length=150), nullable=True),
        sa.Column("ordered_by_practitioner_id", sa.Uuid(), nullable=True),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_discharges_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ordered_by_practitioner_id"],
            ["professionals.id"],
            name=op.f("fk_discharges_ordered_by_practitioner_id_professionals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discharges")),
        sa.UniqueConstraint("hospitalization_id", name=op.f("uq_discharges_hospitalization_id")),
    )
    op.create_index(
        op.f("ix_discharges_ordered_by_practitioner_id"),
        "discharges",
        ["ordered_by_practitioner_id"],
    )

    # Hospitalizations already discharged get the clinical discharge record they implied.
    op.execute(
        """
        INSERT INTO discharges
            (id, hospitalization_id, discharge_type, discharge_reason, ordered_by,
             ordered_at, effective_at, created_at, updated_at)
        SELECT gen_random_uuid(),
               h.id,
               'MEDICAL'::discharge_type,
               'Migrado desde hospitalizations.discharged_at',
               NULL,
               h.clinically_discharged_at,
               h.clinically_discharged_at,
               now(),
               now()
        FROM hospitalizations h
        WHERE h.clinically_discharged_at IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade():
    op.drop_index(op.f("ix_discharges_ordered_by_practitioner_id"), table_name="discharges")
    op.drop_table("discharges")
    op.drop_index(
        "uq_active_discharge_plan_per_hospitalization",
        table_name="discharge_plans",
        postgresql_where=sa.text("status IN ('PLANNED', 'CONFIRMED')"),
    )
    op.drop_index(op.f("ix_discharge_plans_hospitalization_id"), table_name="discharge_plans")
    op.drop_table("discharge_plans")

    bind = op.get_bind()
    for enum_name in ("discharge_type", "discharge_plan_status", "discharge_destination"):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
