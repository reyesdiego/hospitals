"""contacto responsable opcional en la orden médica programada"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_0030"
down_revision = "20260921_0029"
branch_labels = None
depends_on = None


def upgrade():
    # La orden médica programada reserva la cama antes de que el paciente llegue: el
    # contacto se toma cuando se presenta. Para el resto de los orígenes lo exige la API.
    op.alter_column(
        "admissions", "responsible_contact_name", existing_type=sa.String(150), nullable=True
    )
    op.alter_column(
        "admissions", "responsible_contact_phone", existing_type=sa.String(80), nullable=True
    )


def downgrade():
    op.execute(
        "UPDATE admissions SET responsible_contact_name = '' "
        "WHERE responsible_contact_name IS NULL"
    )
    op.execute(
        "UPDATE admissions SET responsible_contact_phone = '' "
        "WHERE responsible_contact_phone IS NULL"
    )
    op.alter_column(
        "admissions", "responsible_contact_phone", existing_type=sa.String(80), nullable=False
    )
    op.alter_column(
        "admissions", "responsible_contact_name", existing_type=sa.String(150), nullable=False
    )
