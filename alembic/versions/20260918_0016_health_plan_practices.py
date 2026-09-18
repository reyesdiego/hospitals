"""practices covered by each health plan, with waiting period and copayment"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0016"
down_revision = "20260918_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "health_plan_practices",
        sa.Column("health_plan_id", sa.Uuid(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        sa.Column("is_covered", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("waiting_period_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "copayment_amount", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False
        ),
        sa.Column("requires_authorization", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "waiting_period_days >= 0",
            name=op.f("ck_health_plan_practices_non_negative_waiting_period"),
        ),
        sa.CheckConstraint(
            "copayment_amount >= 0",
            name=op.f("ck_health_plan_practices_non_negative_copayment"),
        ),
        sa.ForeignKeyConstraint(
            ["health_plan_id"],
            ["health_plans.id"],
            name=op.f("fk_health_plan_practices_health_plan_id_health_plans"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["medical_practices.id"],
            name=op.f("fk_health_plan_practices_practice_id_medical_practices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_plan_practices")),
        sa.UniqueConstraint(
            "health_plan_id", "practice_id", name="uq_health_plan_practices_plan_practice"
        ),
    )
    op.create_index(
        op.f("ix_health_plan_practices_health_plan_id"), "health_plan_practices", ["health_plan_id"]
    )
    op.create_index(
        op.f("ix_health_plan_practices_practice_id"), "health_plan_practices", ["practice_id"]
    )


def downgrade():
    op.drop_index(op.f("ix_health_plan_practices_practice_id"), table_name="health_plan_practices")
    op.drop_index(
        op.f("ix_health_plan_practices_health_plan_id"), table_name="health_plan_practices"
    )
    op.drop_table("health_plan_practices")
