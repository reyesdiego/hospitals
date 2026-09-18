"""what the cartilla of the plan said when the practice was registered"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0017"
down_revision = "20260918_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hospitalization_practices",
        sa.Column("authorization_number", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "hospitalization_practices",
        sa.Column(
            "copayment_amount",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "hospitalization_practices",
        sa.Column("copayment_charge_item_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "hospitalization_practices",
        sa.Column("coverage_override_reason", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_hosp_practices_non_negative_copayment",
        "hospitalization_practices",
        "copayment_amount >= 0",
    )
    op.create_unique_constraint(
        "uq_hosp_practices_copayment_charge_item_id",
        "hospitalization_practices",
        ["copayment_charge_item_id"],
    )
    op.create_foreign_key(
        "fk_hosp_practices_copayment_charge_item_id_charge_items",
        "hospitalization_practices",
        "charge_items",
        ["copayment_charge_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "fk_hosp_practices_copayment_charge_item_id_charge_items",
        "hospitalization_practices",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_hosp_practices_copayment_charge_item_id",
        "hospitalization_practices",
        type_="unique",
    )
    op.drop_constraint(
        "ck_hosp_practices_non_negative_copayment",
        "hospitalization_practices",
        type_="check",
    )
    op.drop_column("hospitalization_practices", "coverage_override_reason")
    op.drop_column("hospitalization_practices", "copayment_charge_item_id")
    op.drop_column("hospitalization_practices", "copayment_amount")
    op.drop_column("hospitalization_practices", "authorization_number")
