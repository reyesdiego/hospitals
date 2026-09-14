"""professionals and specialties"""

from alembic import op
import sqlalchemy as sa

revision = "20260913_0004"
down_revision = "20260803_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "specialties",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specialties")),
        sa.UniqueConstraint("code", name=op.f("uq_specialties_code")),
    )
    op.create_table(
        "professionals",
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("document_number", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_professionals")),
        sa.UniqueConstraint("document_type", "document_number", name="uq_professionals_document"),
    )
    op.create_table(
        "professional_specialties",
        sa.Column("professional_id", sa.Uuid(), nullable=False),
        sa.Column("specialty_id", sa.Uuid(), nullable=False),
        sa.Column("license_number", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["professional_id"], ["professionals.id"], name=op.f("fk_professional_specialties_professional_id_professionals"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["specialty_id"], ["specialties.id"], name=op.f("fk_professional_specialties_specialty_id_specialties"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_professional_specialties")),
        sa.UniqueConstraint("license_number", name="uq_professional_specialties_license_number"),
        sa.UniqueConstraint("professional_id", "specialty_id", name="uq_professional_specialties_professional_specialty"),
    )


def downgrade():
    op.drop_table("professional_specialties")
    op.drop_table("professionals")
    op.drop_table("specialties")
