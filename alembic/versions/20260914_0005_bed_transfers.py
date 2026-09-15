"""bed status and transfers"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260914_0005"
down_revision = "20260913_0004"
branch_labels = None
depends_on = None


def upgrade():
    transfer_status = postgresql.ENUM(
        "COMPLETED",
        "CANCELLED",
        name="bed_transfer_status",
        create_type=False,
    )
    transfer_status.create(op.get_bind(), checkfirst=True)

    bed_status = postgresql.ENUM(
        "AVAILABLE",
        "RESERVED",
        "OCCUPIED",
        "PENDING_CLEANING",
        "BLOCKED",
        "MAINTENANCE",
        name="bed_status",
        create_type=False,
    )
    op.add_column(
        "beds",
        sa.Column(
            "status",
            bed_status,
            server_default="AVAILABLE",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE beds
        SET status = active.status
        FROM (
            SELECT DISTINCT ON (bed_id) bed_id, status
            FROM bed_assignments
            WHERE ended_at IS NULL
            ORDER BY bed_id, started_at DESC
        ) AS active
        WHERE beds.id = active.bed_id
        """
    )
    op.alter_column("beds", "status", server_default=None)

    op.add_column("bed_assignments", sa.Column("assignment_reason", sa.String(length=500), nullable=True))
    op.add_column("bed_assignments", sa.Column("assigned_by", sa.String(length=150), nullable=True))
    op.add_column("bed_assignments", sa.Column("ended_by", sa.String(length=150), nullable=True))

    op.create_table(
        "bed_transfers",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("from_bed_id", sa.Uuid(), nullable=False),
        sa.Column("to_bed_id", sa.Uuid(), nullable=False),
        sa.Column("status", transfer_status, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("requested_by", sa.String(length=150), nullable=True),
        sa.Column("completed_by", sa.String(length=150), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_bed_id"],
            ["beds.id"],
            name=op.f("fk_bed_transfers_from_bed_id_beds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_bed_transfers_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_bed_id"],
            ["beds.id"],
            name=op.f("fk_bed_transfers_to_bed_id_beds"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bed_transfers")),
    )
    op.create_index(op.f("ix_bed_transfers_hospitalization_id"), "bed_transfers", ["hospitalization_id"])
    op.create_index(op.f("ix_bed_transfers_from_bed_id"), "bed_transfers", ["from_bed_id"])
    op.create_index(op.f("ix_bed_transfers_to_bed_id"), "bed_transfers", ["to_bed_id"])


def downgrade():
    op.drop_index(op.f("ix_bed_transfers_to_bed_id"), table_name="bed_transfers")
    op.drop_index(op.f("ix_bed_transfers_from_bed_id"), table_name="bed_transfers")
    op.drop_index(op.f("ix_bed_transfers_hospitalization_id"), table_name="bed_transfers")
    op.drop_table("bed_transfers")
    op.drop_column("bed_assignments", "ended_by")
    op.drop_column("bed_assignments", "assigned_by")
    op.drop_column("bed_assignments", "assignment_reason")
    op.drop_column("beds", "status")
    postgresql.ENUM(name="bed_transfer_status").drop(op.get_bind(), checkfirst=True)
