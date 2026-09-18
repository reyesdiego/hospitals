"""hospitalization account, charge items and lifecycle audit trail"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260917_0011"
down_revision = "20260917_0010"
branch_labels = None
depends_on = None

EVENT_TYPES = (
    "ADMISSION_REQUESTED",
    "ADMISSION_AUTHORIZED",
    "ADMISSION_REJECTED",
    "HOSPITALIZATION_CREATED",
    "SERVICE_ASSIGNED",
    "CARE_TEAM_MEMBER_ASSIGNED",
    "CARE_TEAM_MEMBER_ENDED",
    "BED_RESERVED",
    "BED_RESERVATION_CANCELLED",
    "BED_RESERVATION_EXPIRED",
    "BED_ASSIGNED",
    "PATIENT_TRANSFERRED",
    "BED_RELEASED",
    "DISCHARGE_PLANNED",
    "CLINICAL_DISCHARGE_COMPLETED",
    "PATIENT_PHYSICALLY_DEPARTED",
    "BED_CLEANING_STARTED",
    "BED_AVAILABLE",
    "BED_STATUS_CHANGED",
    "ADMINISTRATIVE_DISCHARGE_COMPLETED",
    "ACCOUNT_READY_FOR_REVIEW",
    "HOSPITALIZATION_CLOSED",
    "HOSPITALIZATION_CANCELLED",
)


def upgrade():
    bind = op.get_bind()
    account_status = postgresql.ENUM(
        "OPEN",
        "READY_FOR_REVIEW",
        "CLOSED",
        "CANCELLED",
        name="account_status",
        create_type=False,
    )
    charge_category = postgresql.ENUM(
        "HOSPITALIZATION_DAY",
        "INTENSIVE_CARE_DAY",
        "MEDICATION",
        "LABORATORY",
        "IMAGING",
        "PROCEDURE",
        "SUPPLY",
        "PROFESSIONAL_FEE",
        "OTHER",
        name="charge_category",
        create_type=False,
    )
    event_type = postgresql.ENUM(*EVENT_TYPES, name="hospitalization_event_type", create_type=False)
    for enum_type in (account_status, charge_category, event_type):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "accounts",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("coverage_id", sa.Uuid(), nullable=True),
        sa.Column("status", account_status, nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="ARS", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_for_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["coverage_id"],
            ["patient_coverages.id"],
            name=op.f("fk_accounts_coverage_id_patient_coverages"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_accounts_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_accounts_patient_id_patients"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("hospitalization_id", name=op.f("uq_accounts_hospitalization_id")),
    )
    op.create_index(op.f("ix_accounts_coverage_id"), "accounts", ["coverage_id"])
    op.create_index(op.f("ix_accounts_patient_id"), "accounts", ["patient_id"])

    op.create_table(
        "charge_items",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("category", charge_category, nullable=False),
        sa.Column("description", sa.String(length=250), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("charged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(length=150), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_charge_items_positive_quantity")),
        sa.CheckConstraint("unit_price >= 0", name=op.f("ck_charge_items_non_negative_unit_price")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_charge_items_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_charge_items")),
    )
    op.create_index(op.f("ix_charge_items_account_id"), "charge_items", ["account_id"])

    op.create_table(
        "hospitalization_events",
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("hospitalization_id", sa.Uuid(), nullable=True),
        sa.Column("admission_id", sa.Uuid(), nullable=True),
        sa.Column("bed_id", sa.Uuid(), nullable=True),
        sa.Column("patient_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=150), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["admission_id"],
            ["admissions.id"],
            name=op.f("fk_hospitalization_events_admission_id_admissions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bed_id"],
            ["beds.id"],
            name=op.f("fk_hospitalization_events_bed_id_beds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_hospitalization_events_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_hospitalization_events_patient_id_patients"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospitalization_events")),
    )
    op.create_index(op.f("ix_hospitalization_events_admission_id"), "hospitalization_events", ["admission_id"])
    op.create_index(op.f("ix_hospitalization_events_bed_id"), "hospitalization_events", ["bed_id"])
    op.create_index(
        op.f("ix_hospitalization_events_hospitalization_id"),
        "hospitalization_events",
        ["hospitalization_id"],
    )
    op.create_index(op.f("ix_hospitalization_events_patient_id"), "hospitalization_events", ["patient_id"])
    op.create_index(
        "ix_hospitalization_events_hospitalization_occurred",
        "hospitalization_events",
        ["hospitalization_id", "occurred_at"],
    )

    # Every existing hospitalization gets its account; closure state follows the
    # hospitalization state, never the other way around.
    op.execute(
        """
        INSERT INTO accounts
            (id, hospitalization_id, patient_id, coverage_id, status, currency,
             opened_at, ready_for_review_at, closed_at, created_at, updated_at)
        SELECT DISTINCT ON (h.id)
               gen_random_uuid(),
               h.id,
               h.patient_id,
               a.coverage_id,
               (CASE
                    WHEN h.status::text = 'CLOSED' THEN 'CLOSED'
                    WHEN h.clinically_discharged_at IS NOT NULL THEN 'READY_FOR_REVIEW'
                    ELSE 'OPEN'
                END)::account_status,
               'ARS',
               COALESCE(h.admitted_at, h.created_at),
               h.clinically_discharged_at,
               CASE WHEN h.status::text = 'CLOSED' THEN h.closed_at END,
               now(),
               now()
        FROM hospitalizations h
        LEFT JOIN admissions a ON a.hospitalization_id = h.id
        ORDER BY h.id, a.created_at
        ON CONFLICT DO NOTHING
        """
    )


def downgrade():
    op.drop_index("ix_hospitalization_events_hospitalization_occurred", table_name="hospitalization_events")
    op.drop_index(op.f("ix_hospitalization_events_patient_id"), table_name="hospitalization_events")
    op.drop_index(op.f("ix_hospitalization_events_hospitalization_id"), table_name="hospitalization_events")
    op.drop_index(op.f("ix_hospitalization_events_bed_id"), table_name="hospitalization_events")
    op.drop_index(op.f("ix_hospitalization_events_admission_id"), table_name="hospitalization_events")
    op.drop_table("hospitalization_events")
    op.drop_index(op.f("ix_charge_items_account_id"), table_name="charge_items")
    op.drop_table("charge_items")
    op.drop_index(op.f("ix_accounts_patient_id"), table_name="accounts")
    op.drop_index(op.f("ix_accounts_coverage_id"), table_name="accounts")
    op.drop_table("accounts")

    bind = op.get_bind()
    for enum_name in ("hospitalization_event_type", "charge_category", "account_status"):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
