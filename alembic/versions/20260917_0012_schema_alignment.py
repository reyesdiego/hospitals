"""align pre-existing schema with the models

The first migrations left ``created_at``/``updated_at`` nullable and skipped the indexes
declared on some foreign keys, so ``alembic revision --autogenerate`` kept reporting drift.
"""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0012"
down_revision = "20260917_0011"
branch_labels = None
depends_on = None

TIMESTAMP_TABLES = (
    "admission_consents",
    "admissions",
    "bed_assignments",
    "bed_transfers",
    "beds",
    "episodes",
    "facilities",
    "hospitalizations",
    "patient_coverages",
    "patients",
    "professional_specialties",
    "professionals",
    "rooms",
    "services",
    "specialties",
)
MISSING_INDEXES = (
    ("ix_bed_assignments_bed_id", "bed_assignments", ["bed_id"]),
    ("ix_bed_assignments_hospitalization_id", "bed_assignments", ["hospitalization_id"]),
    ("ix_beds_facility_id", "beds", ["facility_id"]),
    ("ix_beds_room_id", "beds", ["room_id"]),
    ("ix_hospitalizations_patient_id", "hospitalizations", ["patient_id"]),
    ("ix_rooms_facility_id", "rooms", ["facility_id"]),
)


def upgrade():
    for table in TIMESTAMP_TABLES:
        for column in ("created_at", "updated_at"):
            op.execute(f"UPDATE {table} SET {column} = now() WHERE {column} IS NULL")
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                existing_server_default=sa.text("now()"),
                nullable=False,
            )

    for name, table, columns in MISSING_INDEXES:
        op.create_index(op.f(name), table, columns, unique=False, if_not_exists=True)

    # ``episode_number`` is declared unique and indexed: one unique index covers both.
    op.drop_constraint(op.f("uq_episodes_episode_number"), "episodes", type_="unique")
    op.drop_index(op.f("ix_episodes_episode_number"), table_name="episodes")
    op.create_index(op.f("ix_episodes_episode_number"), "episodes", ["episode_number"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_episodes_episode_number"), table_name="episodes")
    op.create_index(op.f("ix_episodes_episode_number"), "episodes", ["episode_number"], unique=False)
    op.create_unique_constraint(op.f("uq_episodes_episode_number"), "episodes", ["episode_number"])

    for name, table, _columns in MISSING_INDEXES:
        op.drop_index(op.f(name), table_name=table, if_exists=True)

    for table in TIMESTAMP_TABLES:
        for column in ("created_at", "updated_at"):
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                existing_server_default=sa.text("now()"),
                nullable=True,
            )
