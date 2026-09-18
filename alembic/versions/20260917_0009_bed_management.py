"""bed reservations, status history and occupancy-only bed assignments

``bed_assignments`` stops doubling as the bed status log: operational statuses move to
``bed_status_history`` and holds on a bed move to ``bed_reservations``.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260917_0009"
down_revision = "20260917_0008"
branch_labels = None
depends_on = None

BED_STATUS = postgresql.ENUM(name="bed_status", create_type=False)


def upgrade():
    bind = op.get_bind()
    op.execute("ALTER TYPE bed_status ADD VALUE IF NOT EXISTS 'CLEANING' AFTER 'PENDING_CLEANING'")
    op.execute("ALTER TYPE bed_status ADD VALUE IF NOT EXISTS 'OUT_OF_SERVICE' AFTER 'MAINTENANCE'")

    reservation_status = postgresql.ENUM(
        "ACTIVE",
        "COMPLETED",
        "CANCELLED",
        "EXPIRED",
        name="bed_reservation_status",
        create_type=False,
    )
    reservation_status.create(bind, checkfirst=True)

    op.create_table(
        "bed_status_history",
        sa.Column("bed_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", BED_STATUS, nullable=True),
        sa.Column("new_status", BED_STATUS, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.String(length=150), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["bed_id"],
            ["beds.id"],
            name=op.f("fk_bed_status_history_bed_id_beds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bed_status_history")),
    )
    op.create_index(op.f("ix_bed_status_history_bed_id"), "bed_status_history", ["bed_id"])
    op.create_index(
        "ix_bed_status_history_bed_changed",
        "bed_status_history",
        ["bed_id", "changed_at"],
    )

    op.create_table(
        "bed_reservations",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("bed_id", sa.Uuid(), nullable=False),
        sa.Column("status", reservation_status, nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reserved_by", sa.String(length=150), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > reserved_at",
            name=op.f("ck_bed_reservations_expiry_after_reservation"),
        ),
        sa.ForeignKeyConstraint(
            ["bed_id"],
            ["beds.id"],
            name=op.f("fk_bed_reservations_bed_id_beds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_bed_reservations_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bed_reservations")),
    )
    op.create_index(op.f("ix_bed_reservations_bed_id"), "bed_reservations", ["bed_id"])
    op.create_index(
        op.f("ix_bed_reservations_hospitalization_id"),
        "bed_reservations",
        ["hospitalization_id"],
    )
    op.create_index(
        "uq_active_reservation_per_bed",
        "bed_reservations",
        ["bed_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_active_reservation_per_hospitalization",
        "bed_reservations",
        ["hospitalization_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # Rows without hospitalization were operational bed statuses, not occupancy: their
    # history is preserved in bed_status_history instead of being deleted outright.
    op.execute(
        """
        INSERT INTO bed_status_history
            (id, bed_id, previous_status, new_status, changed_at, changed_by, reason, created_at, updated_at)
        SELECT gen_random_uuid(),
               ba.bed_id,
               NULL,
               ba.status,
               ba.started_at,
               ba.assigned_by,
               'Migrado desde bed_assignments',
               now(),
               now()
        FROM bed_assignments ba
        WHERE ba.hospitalization_id IS NULL
        """
    )
    op.execute("DELETE FROM bed_assignments WHERE hospitalization_id IS NULL")

    op.alter_column("bed_assignments", "hospitalization_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index(
        "uq_active_bed_per_hospitalization",
        table_name="bed_assignments",
        postgresql_where=sa.text("hospitalization_id IS NOT NULL AND ended_at IS NULL"),
    )
    op.create_index(
        "uq_active_bed_per_hospitalization",
        "bed_assignments",
        ["hospitalization_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.drop_column("bed_assignments", "status")
    op.create_check_constraint(
        "period",
        "bed_assignments",
        "ended_at IS NULL OR ended_at >= started_at",
    )


def downgrade():
    op.drop_constraint(op.f("ck_bed_assignments_period"), "bed_assignments", type_="check")
    op.add_column(
        "bed_assignments",
        sa.Column("status", BED_STATUS, nullable=True),
    )
    op.execute("UPDATE bed_assignments SET status = 'OCCUPIED' WHERE status IS NULL")
    op.alter_column("bed_assignments", "status", existing_type=BED_STATUS, nullable=False)
    op.drop_index(
        "uq_active_bed_per_hospitalization",
        table_name="bed_assignments",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "uq_active_bed_per_hospitalization",
        "bed_assignments",
        ["hospitalization_id"],
        unique=True,
        postgresql_where=sa.text("hospitalization_id IS NOT NULL AND ended_at IS NULL"),
    )
    op.alter_column("bed_assignments", "hospitalization_id", existing_type=sa.Uuid(), nullable=True)

    op.drop_index(
        "uq_active_reservation_per_hospitalization",
        table_name="bed_reservations",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_index(
        "uq_active_reservation_per_bed",
        table_name="bed_reservations",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_index(op.f("ix_bed_reservations_hospitalization_id"), table_name="bed_reservations")
    op.drop_index(op.f("ix_bed_reservations_bed_id"), table_name="bed_reservations")
    op.drop_table("bed_reservations")

    op.drop_index("ix_bed_status_history_bed_changed", table_name="bed_status_history")
    op.drop_index(op.f("ix_bed_status_history_bed_id"), table_name="bed_status_history")
    op.drop_table("bed_status_history")

    postgresql.ENUM(name="bed_reservation_status").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot remove enum values: CLEANING and OUT_OF_SERVICE stay in bed_status.
