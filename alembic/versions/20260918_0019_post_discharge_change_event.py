"""evento del cambio hecho después del alta médica"""

from alembic import op

revision = "20260918_0019"
down_revision = "20260918_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TYPE hospitalization_event_type ADD VALUE IF NOT EXISTS 'POST_DISCHARGE_CHANGE'"
    )


def downgrade():
    # PostgreSQL no permite sacar valores de un enum: ``POST_DISCHARGE_CHANGE`` queda.
    pass
