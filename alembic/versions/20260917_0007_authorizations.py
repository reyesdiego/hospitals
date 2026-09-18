"""authorizations as first class entities

Authorization stops being a pair of columns on the admission request: every request and
response is now a row, so one admission/hospitalization can hold several authorizations.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260917_0007"
down_revision = "20260917_0006"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # The admission request may now be rejected by the payer.
    op.execute("ALTER TYPE admission_status ADD VALUE IF NOT EXISTS 'REJECTED' AFTER 'ADMITTED'")

    authorization_type = postgresql.ENUM(
        "ADMISSION",
        "EXTENSION",
        "PROCEDURE",
        "TRANSFER",
        "OTHER",
        name="authorization_type",
        create_type=False,
    )
    authorization_state = postgresql.ENUM(
        "REQUESTED",
        "PENDING",
        "AUTHORIZED",
        "REJECTED",
        "EXPIRED",
        "CANCELLED",
        name="authorization_state",
        create_type=False,
    )
    authorization_type.create(bind, checkfirst=True)
    authorization_state.create(bind, checkfirst=True)

    op.create_table(
        "authorizations",
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("admission_id", sa.Uuid(), nullable=True),
        sa.Column("hospitalization_id", sa.Uuid(), nullable=True),
        sa.Column("patient_coverage_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_type", authorization_type, nullable=False),
        sa.Column("authorization_number", sa.String(length=100), nullable=True),
        sa.Column("status", authorization_state, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.String(length=150), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["admission_id"],
            ["admissions.id"],
            name=op.f("fk_authorizations_admission_id_admissions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_authorizations_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_coverage_id"],
            ["patient_coverages.id"],
            name=op.f("fk_authorizations_patient_coverage_id_patient_coverages"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_authorizations_patient_id_patients"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authorizations")),
    )
    op.create_index(op.f("ix_authorizations_admission_id"), "authorizations", ["admission_id"])
    op.create_index(op.f("ix_authorizations_hospitalization_id"), "authorizations", ["hospitalization_id"])
    op.create_index(op.f("ix_authorizations_patient_coverage_id"), "authorizations", ["patient_coverage_id"])
    op.create_index(op.f("ix_authorizations_patient_id"), "authorizations", ["patient_id"])

    op.add_column("admissions", sa.Column("facility_id", sa.Uuid(), nullable=True))
    op.add_column("admissions", sa.Column("responsible_physician_id", sa.Uuid(), nullable=True))
    op.add_column("admissions", sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_admissions_facility_id"), "admissions", ["facility_id"])
    op.create_index(
        op.f("ix_admissions_responsible_physician_id"),
        "admissions",
        ["responsible_physician_id"],
    )
    op.create_foreign_key(
        op.f("fk_admissions_facility_id_facilities"),
        "admissions",
        "facilities",
        ["facility_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_admissions_responsible_physician_id_professionals"),
        "admissions",
        "professionals",
        ["responsible_physician_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute("UPDATE admissions SET requested_at = created_at WHERE requested_at IS NULL")

    # Existing admissions carry their authorization decision in two columns; turn each of
    # them into the authorization row that produced it.
    op.execute(
        """
        INSERT INTO authorizations
            (id, patient_id, admission_id, hospitalization_id, patient_coverage_id,
             authorization_type, authorization_number, status, requested_at, requested_by,
             resolved_at, authorized_at, notes, created_at, updated_at)
        SELECT gen_random_uuid(),
               a.patient_id,
               a.id,
               a.hospitalization_id,
               a.coverage_id,
               'ADMISSION'::authorization_type,
               a.authorization_number,
               (CASE a.authorization_status::text
                    WHEN 'AUTHORIZED' THEN 'AUTHORIZED'
                    WHEN 'REJECTED' THEN 'REJECTED'
                    ELSE 'PENDING'
                END)::authorization_state,
               a.created_at,
               NULL,
               CASE WHEN a.authorization_status::text IN ('AUTHORIZED', 'REJECTED')
                    THEN a.created_at END,
               CASE WHEN a.authorization_status::text = 'AUTHORIZED' THEN a.created_at END,
               'Migrado desde admissions.authorization_status',
               now(),
               now()
        FROM admissions a
        WHERE a.authorization_status::text <> 'NOT_REQUIRED'
        """
    )


def downgrade():
    op.drop_constraint(
        op.f("fk_admissions_responsible_physician_id_professionals"),
        "admissions",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("fk_admissions_facility_id_facilities"), "admissions", type_="foreignkey")
    op.drop_index(op.f("ix_admissions_responsible_physician_id"), table_name="admissions")
    op.drop_index(op.f("ix_admissions_facility_id"), table_name="admissions")
    op.drop_column("admissions", "requested_at")
    op.drop_column("admissions", "responsible_physician_id")
    op.drop_column("admissions", "facility_id")

    op.drop_index(op.f("ix_authorizations_patient_id"), table_name="authorizations")
    op.drop_index(op.f("ix_authorizations_patient_coverage_id"), table_name="authorizations")
    op.drop_index(op.f("ix_authorizations_hospitalization_id"), table_name="authorizations")
    op.drop_index(op.f("ix_authorizations_admission_id"), table_name="authorizations")
    op.drop_table("authorizations")

    bind = op.get_bind()
    postgresql.ENUM(name="authorization_state").drop(bind, checkfirst=True)
    postgresql.ENUM(name="authorization_type").drop(bind, checkfirst=True)
    # PostgreSQL cannot remove a value from an enum: 'REJECTED' stays in admission_status.
