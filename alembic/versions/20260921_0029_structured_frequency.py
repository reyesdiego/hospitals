"""frecuencia estructurada de la medicación"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260921_0029"
down_revision = "20260921_0028"
branch_labels = None
depends_on = None

KINDS = ("INTERVAL", "TIMES", "ONCE", "AS_NEEDED", "CONTINUOUS")


def upgrade():
    kind = postgresql.ENUM(*KINDS, name="schedule_kind", create_type=False)
    kind.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "hospitalization_treatments",
        sa.Column("schedule_kind", kind, server_default="AS_NEEDED", nullable=False),
    )
    op.add_column(
        "hospitalization_treatments",
        sa.Column("interval_hours", sa.Integer(), nullable=True),
    )
    op.add_column(
        "hospitalization_treatments",
        sa.Column("times_of_day", postgresql.ARRAY(sa.Time()), nullable=True),
    )
    # Lo ya cargado queda a demanda: su frecuencia es texto y no se puede adivinar sin
    # inventar horarios que nadie indicó.


def downgrade():
    op.drop_column("hospitalization_treatments", "times_of_day")
    op.drop_column("hospitalization_treatments", "interval_hours")
    op.drop_column("hospitalization_treatments", "schedule_kind")
    postgresql.ENUM(name="schedule_kind").drop(op.get_bind(), checkfirst=True)
