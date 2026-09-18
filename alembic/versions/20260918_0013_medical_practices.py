"""medical practice catalog (nomenclador) and tariffs per payer"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260918_0013"
down_revision = "20260917_0012"
branch_labels = None
depends_on = None

NOMENCLADORES = ("NACIONAL", "NBU", "NU_SSS", "HPGD", "PROPIO")

CHAPTERS = (
    "CONSULTAS",
    "INTERNACION",
    "PRACTICAS_ESPECIALIZADAS",
    "CIRUGIA",
    "OBSTETRICIA",
    "ANESTESIA",
    "LABORATORIO",
    "DIAGNOSTICO_POR_IMAGENES",
    "ANATOMIA_PATOLOGICA",
    "HEMOTERAPIA",
    "KINESIOLOGIA",
    "FONOAUDIOLOGIA",
    "SALUD_MENTAL",
    "ODONTOLOGIA",
    "TRASLADOS",
    "OTROS",
)

PRACTICE_TYPES = (
    "CONSULTA",
    "PRACTICA",
    "CIRUGIA",
    "LABORATORIO",
    "IMAGENES",
    "ANESTESIA",
    "INTERNACION",
    "MODULO",
    "TRASLADO",
    "OTRO",
)

SETTINGS = ("AMBULATORIO", "INTERNACION", "AMBOS")


def upgrade():
    bind = op.get_bind()
    nomenclador = postgresql.ENUM(*NOMENCLADORES, name="nomenclador", create_type=False)
    chapter = postgresql.ENUM(*CHAPTERS, name="practice_chapter", create_type=False)
    practice_type = postgresql.ENUM(*PRACTICE_TYPES, name="practice_type", create_type=False)
    setting = postgresql.ENUM(*SETTINGS, name="practice_setting", create_type=False)
    for enum_type in (nomenclador, chapter, practice_type, setting):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "medical_practices",
        sa.Column("nomenclador", nomenclador, nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("chapter", chapter, nullable=False),
        sa.Column("practice_type", practice_type, nullable=False),
        sa.Column("setting", setting, server_default="AMBOS", nullable=False),
        sa.Column("galeno_units", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
        sa.Column("expense_units", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
        sa.Column("anesthesia_units", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
        sa.Column("biochemical_units", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
        sa.Column("radiology_units", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
        sa.Column("requires_authorization", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("requires_consent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("galeno_units >= 0", name=op.f("ck_medical_practices_non_negative_galeno_units")),
        sa.CheckConstraint("expense_units >= 0", name=op.f("ck_medical_practices_non_negative_expense_units")),
        sa.CheckConstraint(
            "anesthesia_units >= 0",
            name=op.f("ck_medical_practices_non_negative_anesthesia_units"),
        ),
        sa.CheckConstraint(
            "biochemical_units >= 0",
            name=op.f("ck_medical_practices_non_negative_biochemical_units"),
        ),
        sa.CheckConstraint(
            "radiology_units >= 0",
            name=op.f("ck_medical_practices_non_negative_radiology_units"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name=op.f("ck_medical_practices_valid_period"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medical_practices")),
        sa.UniqueConstraint("nomenclador", "code", name="uq_medical_practices_nomenclador_code"),
    )
    op.create_index(op.f("ix_medical_practices_nomenclador"), "medical_practices", ["nomenclador"])
    op.create_index(op.f("ix_medical_practices_chapter"), "medical_practices", ["chapter"])

    op.create_table(
        "medical_practice_tariffs",
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        sa.Column("payer_id", sa.Uuid(), nullable=True),
        sa.Column("health_plan_id", sa.Uuid(), nullable=True),
        sa.Column("unit_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("professional_fee", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("expense_amount", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("coinsurance", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="ARS", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "unit_value IS NULL OR unit_value >= 0",
            name=op.f("ck_medical_practice_tariffs_non_negative_unit_value"),
        ),
        sa.CheckConstraint(
            "professional_fee >= 0",
            name=op.f("ck_medical_practice_tariffs_non_negative_professional_fee"),
        ),
        sa.CheckConstraint(
            "expense_amount >= 0",
            name=op.f("ck_medical_practice_tariffs_non_negative_expense_amount"),
        ),
        sa.CheckConstraint(
            "total_amount >= 0",
            name=op.f("ck_medical_practice_tariffs_non_negative_total_amount"),
        ),
        sa.CheckConstraint(
            "coinsurance >= 0",
            name=op.f("ck_medical_practice_tariffs_non_negative_coinsurance"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name=op.f("ck_medical_practice_tariffs_valid_period"),
        ),
        sa.ForeignKeyConstraint(
            ["health_plan_id"],
            ["health_plans.id"],
            name=op.f("fk_medical_practice_tariffs_health_plan_id_health_plans"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payer_id"],
            ["payers.id"],
            name=op.f("fk_medical_practice_tariffs_payer_id_payers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["medical_practices.id"],
            name=op.f("fk_medical_practice_tariffs_practice_id_medical_practices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medical_practice_tariffs")),
    )
    op.create_index(
        op.f("ix_medical_practice_tariffs_practice_id"), "medical_practice_tariffs", ["practice_id"]
    )
    op.create_index(
        op.f("ix_medical_practice_tariffs_payer_id"), "medical_practice_tariffs", ["payer_id"]
    )
    op.create_index(
        op.f("ix_medical_practice_tariffs_health_plan_id"),
        "medical_practice_tariffs",
        ["health_plan_id"],
    )
    # The institutional tariff has payer_id and health_plan_id NULL, so the uniqueness of the
    # scope only holds if NULLs are compared as equal.
    op.create_index(
        "uq_medical_practice_tariffs_scope_valid_from",
        "medical_practice_tariffs",
        ["practice_id", "payer_id", "health_plan_id", "valid_from"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade():
    op.drop_index("uq_medical_practice_tariffs_scope_valid_from", table_name="medical_practice_tariffs")
    op.drop_index(op.f("ix_medical_practice_tariffs_health_plan_id"), table_name="medical_practice_tariffs")
    op.drop_index(op.f("ix_medical_practice_tariffs_payer_id"), table_name="medical_practice_tariffs")
    op.drop_index(op.f("ix_medical_practice_tariffs_practice_id"), table_name="medical_practice_tariffs")
    op.drop_table("medical_practice_tariffs")
    op.drop_index(op.f("ix_medical_practices_chapter"), table_name="medical_practices")
    op.drop_index(op.f("ix_medical_practices_nomenclador"), table_name="medical_practices")
    op.drop_table("medical_practices")

    bind = op.get_bind()
    for enum_name in ("practice_setting", "practice_type", "practice_chapter", "nomenclador"):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
