"""voiding a charge of the account instead of deleting it"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260918_0015"
down_revision = "20260918_0014"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    op.execute(
        "ALTER TYPE hospitalization_event_type ADD VALUE IF NOT EXISTS 'CHARGE_ITEM_VOIDED'"
    )

    charge_item_status = postgresql.ENUM(
        "ACTIVE",
        "VOID",
        name="charge_item_status",
        create_type=False,
    )
    charge_item_status.create(bind, checkfirst=True)

    op.add_column(
        "charge_items",
        sa.Column("status", charge_item_status, server_default="ACTIVE", nullable=False),
    )
    op.add_column("charge_items", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("charge_items", sa.Column("voided_by", sa.String(length=150), nullable=True))
    op.add_column("charge_items", sa.Column("void_reason", sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column("charge_items", "void_reason")
    op.drop_column("charge_items", "voided_by")
    op.drop_column("charge_items", "voided_at")
    op.drop_column("charge_items", "status")

    bind = op.get_bind()
    postgresql.ENUM(name="charge_item_status").drop(bind, checkfirst=True)
    # PostgreSQL cannot remove values from an enum: ``CHARGE_ITEM_VOIDED`` stays.
