"""patient identifiers, contacts and normalized coverage

Adds the external-identifier and contact tables for patients and turns the free text
payer/plan of ``patient_coverages`` into optional references to registered payers/plans.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260917_0006"
down_revision = "20260914_0005"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    identifier_type = postgresql.ENUM(
        "DNI",
        "PASSPORT",
        "MEDICAL_RECORD_NUMBER",
        "SOCIAL_SECURITY",
        "EXTERNAL",
        "OTHER",
        name="patient_identifier_type",
        create_type=False,
    )
    coverage_status = postgresql.ENUM(
        "ACTIVE",
        "INACTIVE",
        "EXPIRED",
        name="coverage_status",
        create_type=False,
    )
    identifier_type.create(bind, checkfirst=True)
    coverage_status.create(bind, checkfirst=True)

    op.create_table(
        "payers",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("tax_id", sa.String(length=40), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payers")),
        sa.UniqueConstraint("code", name=op.f("uq_payers_code")),
    )
    op.create_table(
        "health_plans",
        sa.Column("payer_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["payer_id"],
            ["payers.id"],
            name=op.f("fk_health_plans_payer_id_payers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_plans")),
        sa.UniqueConstraint("payer_id", "code", name="uq_health_plans_payer_code"),
    )
    op.create_index(op.f("ix_health_plans_payer_id"), "health_plans", ["payer_id"])

    op.create_table(
        "patient_identifiers",
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("identifier_type", identifier_type, nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("issuer", sa.String(length=120), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_patient_identifiers_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_identifiers")),
        sa.UniqueConstraint("identifier_type", "value", name="uq_patient_identifiers_type_value"),
    )
    op.create_index(op.f("ix_patient_identifiers_patient_id"), "patient_identifiers", ["patient_id"])
    op.create_index(op.f("ix_patient_identifiers_value"), "patient_identifiers", ["value"])

    op.create_table(
        "patient_contacts",
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("relationship_to_patient", sa.String(length=80), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_patient_contacts_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_contacts")),
    )
    op.create_index(op.f("ix_patient_contacts_patient_id"), "patient_contacts", ["patient_id"])

    # The document already loaded on each patient becomes its primary external identifier.
    op.execute(
        """
        INSERT INTO patient_identifiers
            (id, patient_id, identifier_type, value, issuer, is_primary, created_at, updated_at)
        SELECT gen_random_uuid(),
               p.id,
               (CASE upper(p.document_type)
                    WHEN 'DNI' THEN 'DNI'
                    WHEN 'PASAPORTE' THEN 'PASSPORT'
                    WHEN 'PASSPORT' THEN 'PASSPORT'
                    WHEN 'CUIL' THEN 'SOCIAL_SECURITY'
                    WHEN 'CUIT' THEN 'SOCIAL_SECURITY'
                    WHEN 'HISTORIA_CLINICA' THEN 'MEDICAL_RECORD_NUMBER'
                    ELSE 'EXTERNAL'
                END)::patient_identifier_type,
               p.document_number,
               p.document_type,
               true,
               now(),
               now()
        FROM patients p
        ON CONFLICT DO NOTHING
        """
    )

    op.add_column("patient_coverages", sa.Column("payer_id", sa.Uuid(), nullable=True))
    op.add_column("patient_coverages", sa.Column("health_plan_id", sa.Uuid(), nullable=True))
    op.add_column("patient_coverages", sa.Column("valid_from", sa.Date(), nullable=True))
    op.add_column("patient_coverages", sa.Column("valid_until", sa.Date(), nullable=True))
    op.add_column(
        "patient_coverages",
        sa.Column("status", coverage_status, server_default="ACTIVE", nullable=False),
    )
    op.create_index(op.f("ix_patient_coverages_payer_id"), "patient_coverages", ["payer_id"])
    op.create_index(op.f("ix_patient_coverages_health_plan_id"), "patient_coverages", ["health_plan_id"])
    op.create_foreign_key(
        op.f("fk_patient_coverages_payer_id_payers"),
        "patient_coverages",
        "payers",
        ["payer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_patient_coverages_health_plan_id_health_plans"),
        "patient_coverages",
        "health_plans",
        ["health_plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint(
        op.f("fk_patient_coverages_health_plan_id_health_plans"),
        "patient_coverages",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_patient_coverages_payer_id_payers"),
        "patient_coverages",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_patient_coverages_health_plan_id"), table_name="patient_coverages")
    op.drop_index(op.f("ix_patient_coverages_payer_id"), table_name="patient_coverages")
    op.drop_column("patient_coverages", "status")
    op.drop_column("patient_coverages", "valid_until")
    op.drop_column("patient_coverages", "valid_from")
    op.drop_column("patient_coverages", "health_plan_id")
    op.drop_column("patient_coverages", "payer_id")

    op.drop_index(op.f("ix_patient_contacts_patient_id"), table_name="patient_contacts")
    op.drop_table("patient_contacts")
    op.drop_index(op.f("ix_patient_identifiers_value"), table_name="patient_identifiers")
    op.drop_index(op.f("ix_patient_identifiers_patient_id"), table_name="patient_identifiers")
    op.drop_table("patient_identifiers")
    op.drop_index(op.f("ix_health_plans_payer_id"), table_name="health_plans")
    op.drop_table("health_plans")
    op.drop_table("payers")

    bind = op.get_bind()
    postgresql.ENUM(name="coverage_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="patient_identifier_type").drop(bind, checkfirst=True)
