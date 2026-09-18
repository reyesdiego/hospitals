"""carencia por defecto de la práctica, que cada plan puede pactar distinta"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0018"
down_revision = "20260918_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "medical_practices",
        sa.Column(
            "default_waiting_period_days", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.create_check_constraint(
        "non_negative_waiting_period",
        "medical_practices",
        "default_waiting_period_days >= 0",
    )

    # En la cartilla, vacío pasa a significar "rige la carencia de la práctica". Las filas
    # existentes tenían un valor explícito, así que se conservan como están.
    op.drop_constraint(
        "non_negative_waiting_period",
        "health_plan_practices",
        type_="check",
    )
    op.alter_column(
        "health_plan_practices",
        "waiting_period_days",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )
    op.create_check_constraint(
        "non_negative_waiting_period",
        "health_plan_practices",
        "waiting_period_days IS NULL OR waiting_period_days >= 0",
    )


def downgrade():
    op.execute("UPDATE health_plan_practices SET waiting_period_days = 0 WHERE waiting_period_days IS NULL")
    op.drop_constraint(
        "non_negative_waiting_period",
        "health_plan_practices",
        type_="check",
    )
    op.alter_column(
        "health_plan_practices",
        "waiting_period_days",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="0",
    )
    op.create_check_constraint(
        "non_negative_waiting_period",
        "health_plan_practices",
        "waiting_period_days >= 0",
    )

    op.drop_constraint(
        "non_negative_waiting_period", "medical_practices", type_="check"
    )
    op.drop_column("medical_practices", "default_waiting_period_days")
