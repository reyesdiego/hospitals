"""rooms unique code per facility"""

from alembic import op

revision = "20260803_0003"
down_revision = "20260803_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uq_rooms_facility_code", "rooms", ["facility_id", "code"], unique=True)


def downgrade():
    op.drop_index("uq_rooms_facility_code", table_name="rooms")
