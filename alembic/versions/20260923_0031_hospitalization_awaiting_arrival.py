"""internación programada esperando que el paciente llegue"""

from alembic import op

revision = "20260923_0031"
down_revision = "20260923_0030"
branch_labels = None
depends_on = None


def upgrade():
    # El valor nuevo tiene que estar confirmado antes de poder usarlo en el UPDATE.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE hospitalization_status ADD VALUE IF NOT EXISTS 'AWAITING_ARRIVAL' "
            "BEFORE 'PENDING_BED'"
        )
    # Las órdenes médicas programadas que todavía no ocuparon cama: el paciente no llegó.
    op.execute(
        """
        UPDATE hospitalizations AS h
        SET status = 'AWAITING_ARRIVAL'
        FROM admissions AS a
        WHERE a.hospitalization_id = h.id
          AND a.origin = 'SCHEDULED_MEDICAL_ORDER'
          AND h.status = 'PENDING_BED'
          AND h.admitted_at IS NULL
        """
    )


def downgrade():
    # PostgreSQL no quita valores de un enum: se deja el valor y se vuelve al estado anterior.
    op.execute(
        "UPDATE hospitalizations SET status = 'PENDING_BED' WHERE status = 'AWAITING_ARRIVAL'"
    )
