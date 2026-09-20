"""quién dio la práctica por realizada en el sistema"""

import sqlalchemy as sa

from alembic import op

revision = "20260919_0022"
down_revision = "20260919_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hospitalization_practices",
        sa.Column("performed_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "hospitalization_practices",
        sa.Column("performed_by_user_name", sa.String(length=150), nullable=True),
    )
    op.create_index(
        op.f("ix_hospitalization_practices_performed_by_user_id"),
        "hospitalization_practices",
        ["performed_by_user_id"],
    )
    op.create_foreign_key(
        "fk_hosp_practices_performed_by_user_id_users",
        "hospitalization_practices",
        "users",
        ["performed_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint(
        "fk_hosp_practices_performed_by_user_id_users",
        "hospitalization_practices",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_hospitalization_practices_performed_by_user_id"),
        table_name="hospitalization_practices",
    )
    op.drop_column("hospitalization_practices", "performed_by_user_name")
    op.drop_column("hospitalization_practices", "performed_by_user_id")
