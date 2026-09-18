"""practices performed during a hospitalization, linked to the charges of the account"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260918_0014"
down_revision = "20260918_0013"
branch_labels = None
depends_on = None

NEW_EVENT_TYPES = ("PRACTICE_ORDERED", "PRACTICE_PERFORMED", "PRACTICE_CANCELLED")


def upgrade():
    bind = op.get_bind()
    for value in NEW_EVENT_TYPES:
        op.execute(
            f"ALTER TYPE hospitalization_event_type ADD VALUE IF NOT EXISTS '{value}'"
        )

    order_status = postgresql.ENUM(
        "REQUESTED",
        "PERFORMED",
        "CANCELLED",
        name="practice_order_status",
        create_type=False,
    )
    order_status.create(bind, checkfirst=True)

    # A charge can now point at the practice it comes from.
    op.add_column("charge_items", sa.Column("practice_id", sa.Uuid(), nullable=True))
    op.add_column("charge_items", sa.Column("practice_code", sa.String(length=20), nullable=True))
    op.create_foreign_key(
        op.f("fk_charge_items_practice_id_medical_practices"),
        "charge_items",
        "medical_practices",
        ["practice_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_charge_items_practice_id"), "charge_items", ["practice_id"])

    op.create_table(
        "hospitalization_practices",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        sa.Column("practice_code", sa.String(length=20), nullable=False),
        sa.Column("practice_name", sa.String(length=250), nullable=False),
        sa.Column("prescribed_by_id", sa.Uuid(), nullable=False),
        sa.Column("performed_by_id", sa.Uuid(), nullable=True),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("charge_item_id", sa.Uuid(), nullable=True),
        sa.Column("status", order_status, server_default="REQUESTED", nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), server_default="1", nullable=False),
        sa.Column("prescribed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indication", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_hospitalization_practices_positive_quantity")),
        sa.ForeignKeyConstraint(
            ["charge_item_id"],
            ["charge_items.id"],
            name=op.f("fk_hospitalization_practices_charge_item_id_charge_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_hospitalization_practices_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by_id"],
            ["professionals.id"],
            name=op.f("fk_hospitalization_practices_performed_by_id_professionals"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["medical_practices.id"],
            name=op.f("fk_hospitalization_practices_practice_id_medical_practices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prescribed_by_id"],
            ["professionals.id"],
            name=op.f("fk_hospitalization_practices_prescribed_by_id_professionals"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_hospitalization_practices_service_id_services"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospitalization_practices")),
        sa.UniqueConstraint("charge_item_id", name=op.f("uq_hospitalization_practices_charge_item_id")),
    )
    op.create_index(
        op.f("ix_hospitalization_practices_hospitalization_id"),
        "hospitalization_practices",
        ["hospitalization_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_practices_practice_id"),
        "hospitalization_practices",
        ["practice_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_practices_prescribed_by_id"),
        "hospitalization_practices",
        ["prescribed_by_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_practices_performed_by_id"),
        "hospitalization_practices",
        ["performed_by_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_practices_service_id"),
        "hospitalization_practices",
        ["service_id"],
    )
    op.create_index(
        "ix_hospitalization_practices_hospitalization_prescribed",
        "hospitalization_practices",
        ["hospitalization_id", "prescribed_at"],
    )


def downgrade():
    op.drop_index(
        "ix_hospitalization_practices_hospitalization_prescribed",
        table_name="hospitalization_practices",
    )
    for column in ("service_id", "performed_by_id", "prescribed_by_id", "practice_id", "hospitalization_id"):
        op.drop_index(
            op.f(f"ix_hospitalization_practices_{column}"),
            table_name="hospitalization_practices",
        )
    op.drop_table("hospitalization_practices")

    op.drop_index(op.f("ix_charge_items_practice_id"), table_name="charge_items")
    op.drop_constraint(
        op.f("fk_charge_items_practice_id_medical_practices"),
        "charge_items",
        type_="foreignkey",
    )
    op.drop_column("charge_items", "practice_code")
    op.drop_column("charge_items", "practice_id")

    bind = op.get_bind()
    postgresql.ENUM(name="practice_order_status").drop(bind, checkfirst=True)
    # PostgreSQL cannot remove values from an enum: the practice event types stay.
