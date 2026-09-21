"""catálogo CIE-10 de diagnósticos"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260920_0025"
down_revision = "20260920_0024"
branch_labels = None
depends_on = None

LEVELS = ("CHAPTER", "BLOCK", "CATEGORY", "SUBCATEGORY")


def upgrade():
    bind = op.get_bind()
    level = postgresql.ENUM(*LEVELS, name="diagnosis_level", create_type=False)
    level.create(bind, checkfirst=True)

    op.create_table(
        "diagnosis_codes",
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("level", level, nullable=False),
        sa.Column("parent_code", sa.String(length=10), nullable=True),
        sa.Column("chapter_code", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis_codes")),
        sa.UniqueConstraint("code", name=op.f("uq_diagnosis_codes_code")),
        sa.ForeignKeyConstraint(
            ["parent_code"],
            ["diagnosis_codes.code"],
            name=op.f("fk_diagnosis_codes_parent_code_diagnosis_codes"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index(op.f("ix_diagnosis_codes_parent_code"), "diagnosis_codes", ["parent_code"])
    op.create_index(op.f("ix_diagnosis_codes_chapter_code"), "diagnosis_codes", ["chapter_code"])
    op.create_index("ix_diagnosis_codes_level_code", "diagnosis_codes", ["level", "code"])


def downgrade():
    op.drop_index("ix_diagnosis_codes_level_code", table_name="diagnosis_codes")
    op.drop_index(op.f("ix_diagnosis_codes_chapter_code"), table_name="diagnosis_codes")
    op.drop_index(op.f("ix_diagnosis_codes_parent_code"), table_name="diagnosis_codes")
    op.drop_table("diagnosis_codes")
    postgresql.ENUM(name="diagnosis_level").drop(op.get_bind(), checkfirst=True)
