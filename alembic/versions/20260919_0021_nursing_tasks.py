"""prácticas que ejecuta enfermería"""

import sqlalchemy as sa

from alembic import op

revision = "20260919_0021"
down_revision = "20260918_0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "medical_practices",
        sa.Column("is_nursing_task", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "ix_medical_practices_nursing", "medical_practices", ["is_nursing_task"]
    )


def downgrade():
    op.drop_index("ix_medical_practices_nursing", table_name="medical_practices")
    op.drop_column("medical_practices", "is_nursing_task")
