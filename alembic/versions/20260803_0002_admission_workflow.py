"""admission workflow"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260803_0002"
down_revision = "20260731_0001"
branch_labels = None
depends_on = None


def upgrade():
    admission_origin = postgresql.ENUM(
        "EMERGENCY_ROOM",
        "OUTPATIENT_CLINIC",
        "SCHEDULED_SURGERY",
        "EXTERNAL_REFERRAL",
        "HOME_HOSPITALIZATION",
        "SPECIAL_CARE_UNIT",
        "SCHEDULED_MEDICAL_ORDER",
        name="admission_origin",
        create_type=False,
    )
    admission_type = postgresql.ENUM(
        "PRE_ADMISSION",
        "SCHEDULED",
        "EMERGENCY",
        name="admission_type",
        create_type=False,
    )
    admission_status = postgresql.ENUM(
        "PRE_ADMITTED",
        "PENDING_AUTHORIZATION",
        "PENDING_BED",
        "ADMITTED",
        "ADMINISTRATIVE_DISCHARGE",
        "CANCELLED",
        name="admission_status",
        create_type=False,
    )
    authorization_status = postgresql.ENUM(
        "NOT_REQUIRED",
        "PENDING",
        "AUTHORIZED",
        "REJECTED",
        name="authorization_status",
        create_type=False,
    )
    episode_status = postgresql.ENUM(
        "OPEN",
        "CLOSED",
        "CANCELLED",
        name="episode_status",
        create_type=False,
    )
    consent_type = postgresql.ENUM(
        "GENERAL_ADMISSION",
        "DATA_PROCESSING",
        "PROCEDURE",
        "ANESTHESIA",
        "TRANSFER",
        name="consent_type",
        create_type=False,
    )

    bind = op.get_bind()
    for enum in (
        admission_origin,
        admission_type,
        admission_status,
        authorization_status,
        episode_status,
        consent_type,
    ):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "patient_coverages",
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payer_name", sa.String(150), nullable=False),
        sa.Column("plan_name", sa.String(150), nullable=True),
        sa.Column("member_number", sa.String(80), nullable=True),
        sa.Column("authorization_required", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_patient_coverages_patient_id", "patient_coverages", ["patient_id"])

    op.create_table(
        "episodes",
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("episode_number", sa.String(40), nullable=False, unique=True),
        sa.Column("status", episode_status, nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_episodes_patient_id", "episodes", ["patient_id"])
    op.create_index("ix_episodes_episode_number", "episodes", ["episode_number"])

    op.create_table(
        "admissions",
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("episode_id", sa.Uuid(), sa.ForeignKey("episodes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("hospitalization_id", sa.Uuid(), sa.ForeignKey("hospitalizations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("coverage_id", sa.Uuid(), sa.ForeignKey("patient_coverages.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("requesting_service_id", sa.Uuid(), sa.ForeignKey("services.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("requested_bed_id", sa.Uuid(), sa.ForeignKey("beds.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("origin", admission_origin, nullable=False),
        sa.Column("admission_type", admission_type, nullable=False),
        sa.Column("status", admission_status, nullable=False),
        sa.Column("identity_validated", sa.Boolean(), nullable=False),
        sa.Column("duplicate_checked", sa.Boolean(), nullable=False),
        sa.Column("authorization_status", authorization_status, nullable=False),
        sa.Column("authorization_number", sa.String(100), nullable=True),
        sa.Column("responsible_contact_name", sa.String(150), nullable=False),
        sa.Column("responsible_contact_phone", sa.String(80), nullable=False),
        sa.Column("responsible_contact_relationship", sa.String(80), nullable=True),
        sa.Column("admission_reason", sa.String(500), nullable=False),
        sa.Column("responsible_physician", sa.String(150), nullable=False),
        sa.Column("presumptive_diagnosis", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("administrative_discharged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admissions_patient_id", "admissions", ["patient_id"])
    op.create_index("ix_admissions_episode_id", "admissions", ["episode_id"])
    op.create_index("ix_admissions_hospitalization_id", "admissions", ["hospitalization_id"])
    op.create_index("ix_admissions_coverage_id", "admissions", ["coverage_id"])
    op.create_index("ix_admissions_requesting_service_id", "admissions", ["requesting_service_id"])
    op.create_index("ix_admissions_requested_bed_id", "admissions", ["requested_bed_id"])
    op.create_index(
        "ix_admissions_patient_status_type",
        "admissions",
        ["patient_id", "status", "admission_type"],
    )

    op.create_table(
        "admission_consents",
        sa.Column("admission_id", sa.Uuid(), sa.ForeignKey("admissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consent_type", consent_type, nullable=False),
        sa.Column("signed_by", sa.String(150), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admission_consents_admission_id", "admission_consents", ["admission_id"])


def downgrade():
    op.drop_table("admission_consents")
    op.drop_table("admissions")
    op.drop_table("episodes")
    op.drop_table("patient_coverages")
    bind = op.get_bind()
    for enum_name in (
        "consent_type",
        "episode_status",
        "authorization_status",
        "admission_status",
        "admission_type",
        "admission_origin",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
