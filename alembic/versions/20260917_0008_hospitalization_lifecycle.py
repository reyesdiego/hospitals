"""hospitalization lifecycle, responsible service history and care team

Splits the single ``discharged_at`` into the distinct lifecycle moments (clinical discharge,
physical departure, administrative discharge, closure) and moves the relationships that
change over time out of ``hospitalizations``.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260917_0008"
down_revision = "20260917_0007"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    op.execute(
        "ALTER TYPE hospitalization_status ADD VALUE IF NOT EXISTS 'DISCHARGE_PLANNED' "
        "BEFORE 'CLINICALLY_DISCHARGED'"
    )
    op.execute(
        "ALTER TYPE hospitalization_status ADD VALUE IF NOT EXISTS "
        "'ADMINISTRATIVELY_DISCHARGED' AFTER 'CLINICALLY_DISCHARGED'"
    )

    care_team_role = postgresql.ENUM(
        "ATTENDING_PHYSICIAN",
        "SPECIALIST",
        "RESIDENT",
        "NURSE",
        "OTHER",
        name="care_team_role",
        create_type=False,
    )
    care_team_role.create(bind, checkfirst=True)

    op.add_column("episodes", sa.Column("facility_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_episodes_facility_id"), "episodes", ["facility_id"])
    op.create_foreign_key(
        op.f("fk_episodes_facility_id_facilities"),
        "episodes",
        "facilities",
        ["facility_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column("hospitalizations", sa.Column("episode_id", sa.Uuid(), nullable=True))
    op.add_column("hospitalizations", sa.Column("facility_id", sa.Uuid(), nullable=True))
    op.add_column(
        "hospitalizations",
        sa.Column(
            "admission_type",
            postgresql.ENUM(name="admission_type", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "hospitalizations",
        sa.Column("clinically_discharged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hospitalizations",
        sa.Column("physically_departed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hospitalizations",
        sa.Column("administratively_discharged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("hospitalizations", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_hospitalizations_episode_id"), "hospitalizations", ["episode_id"])
    op.create_index(op.f("ix_hospitalizations_facility_id"), "hospitalizations", ["facility_id"])
    op.create_foreign_key(
        op.f("fk_hospitalizations_episode_id_episodes"),
        "hospitalizations",
        "episodes",
        ["episode_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_hospitalizations_facility_id_facilities"),
        "hospitalizations",
        "facilities",
        ["facility_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Link every hospitalization to the episode/facility/type known by its admission request.
    op.execute(
        """
        UPDATE hospitalizations h
        SET episode_id = a.episode_id,
            admission_type = a.admission_type,
            facility_id = COALESCE(
                (SELECT b.facility_id
                   FROM bed_assignments ba
                   JOIN beds b ON b.id = ba.bed_id
                  WHERE ba.hospitalization_id = h.id
                  ORDER BY ba.started_at DESC
                  LIMIT 1),
                (SELECT b2.facility_id FROM beds b2 WHERE b2.id = a.requested_bed_id)
            )
        FROM admissions a
        WHERE a.hospitalization_id = h.id
        """
    )
    op.execute(
        """
        UPDATE episodes e
        SET facility_id = h.facility_id
        FROM hospitalizations h
        WHERE h.episode_id = e.id AND h.facility_id IS NOT NULL
        """
    )
    op.execute(
        "UPDATE hospitalizations SET clinically_discharged_at = discharged_at "
        "WHERE discharged_at IS NOT NULL"
    )
    # Before this change the bed was released together with the clinical discharge, so the
    # end of the last bed assignment is the physical departure of the patient.
    op.execute(
        """
        UPDATE hospitalizations h
        SET physically_departed_at = last_assignment.ended_at
        FROM (
            SELECT hospitalization_id, max(ended_at) AS ended_at
            FROM bed_assignments
            WHERE hospitalization_id IS NOT NULL AND ended_at IS NOT NULL
            GROUP BY hospitalization_id
        ) AS last_assignment
        WHERE last_assignment.hospitalization_id = h.id
          AND h.status::text IN ('CLINICALLY_DISCHARGED', 'CLOSED')
          AND NOT EXISTS (
              SELECT 1 FROM bed_assignments ba
              WHERE ba.hospitalization_id = h.id AND ba.ended_at IS NULL
          )
        """
    )
    op.execute(
        """
        UPDATE hospitalizations h
        SET administratively_discharged_at = a.administrative_discharged_at,
            closed_at = a.administrative_discharged_at
        FROM admissions a
        WHERE a.hospitalization_id = h.id
          AND h.status::text = 'CLOSED'
          AND a.administrative_discharged_at IS NOT NULL
        """
    )
    op.drop_column("hospitalizations", "discharged_at")

    op.create_table(
        "hospitalization_service_assignments",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("assigned_by", sa.String(length=150), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name="fk_hosp_service_assignments_hospitalization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_hospitalization_service_assignments_service_id_services"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospitalization_service_assignments")),
    )
    op.create_index(
        op.f("ix_hospitalization_service_assignments_hospitalization_id"),
        "hospitalization_service_assignments",
        ["hospitalization_id"],
    )
    op.create_index(
        op.f("ix_hospitalization_service_assignments_service_id"),
        "hospitalization_service_assignments",
        ["service_id"],
    )
    op.create_index(
        "uq_active_service_per_hospitalization",
        "hospitalization_service_assignments",
        ["hospitalization_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    # The requesting service of the admission becomes the first responsible service.
    op.execute(
        """
        INSERT INTO hospitalization_service_assignments
            (id, hospitalization_id, service_id, started_at, ended_at, reason, created_at, updated_at)
        SELECT DISTINCT ON (h.id)
               gen_random_uuid(),
               h.id,
               a.requesting_service_id,
               COALESCE(h.admitted_at, h.created_at),
               CASE WHEN h.status::text IN ('CLINICALLY_DISCHARGED', 'CLOSED')
                    THEN GREATEST(
                        COALESCE(h.clinically_discharged_at, h.created_at),
                        COALESCE(h.admitted_at, h.created_at)
                    )
               END,
               'Servicio solicitante de la admision',
               now(),
               now()
        FROM hospitalizations h
        JOIN admissions a ON a.hospitalization_id = h.id
        WHERE a.requesting_service_id IS NOT NULL
        ORDER BY h.id, a.created_at
        ON CONFLICT DO NOTHING
        """
    )

    op.create_table(
        "care_teams",
        sa.Column("hospitalization_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["hospitalization_id"],
            ["hospitalizations.id"],
            name=op.f("fk_care_teams_hospitalization_id_hospitalizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_teams")),
        sa.UniqueConstraint("hospitalization_id", name=op.f("uq_care_teams_hospitalization_id")),
    )
    op.create_table(
        "care_team_members",
        sa.Column("care_team_id", sa.Uuid(), nullable=False),
        sa.Column("practitioner_id", sa.Uuid(), nullable=False),
        sa.Column("role", care_team_role, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["care_team_id"],
            ["care_teams.id"],
            name=op.f("fk_care_team_members_care_team_id_care_teams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["practitioner_id"],
            ["professionals.id"],
            name=op.f("fk_care_team_members_practitioner_id_professionals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_team_members")),
    )
    op.create_index(op.f("ix_care_team_members_care_team_id"), "care_team_members", ["care_team_id"])
    op.create_index(
        op.f("ix_care_team_members_practitioner_id"),
        "care_team_members",
        ["practitioner_id"],
    )
    op.create_index(
        "uq_active_care_team_member_role",
        "care_team_members",
        ["care_team_id", "practitioner_id", "role"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "uq_active_attending_physician",
        "care_team_members",
        ["care_team_id"],
        unique=True,
        postgresql_where=sa.text("role = 'ATTENDING_PHYSICIAN' AND ended_at IS NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_active_attending_physician",
        table_name="care_team_members",
        postgresql_where=sa.text("role = 'ATTENDING_PHYSICIAN' AND ended_at IS NULL"),
    )
    op.drop_index(
        "uq_active_care_team_member_role",
        table_name="care_team_members",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.drop_index(op.f("ix_care_team_members_practitioner_id"), table_name="care_team_members")
    op.drop_index(op.f("ix_care_team_members_care_team_id"), table_name="care_team_members")
    op.drop_table("care_team_members")
    op.drop_table("care_teams")

    op.drop_index(
        "uq_active_service_per_hospitalization",
        table_name="hospitalization_service_assignments",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_hospitalization_service_assignments_service_id"),
        table_name="hospitalization_service_assignments",
    )
    op.drop_index(
        op.f("ix_hospitalization_service_assignments_hospitalization_id"),
        table_name="hospitalization_service_assignments",
    )
    op.drop_table("hospitalization_service_assignments")

    op.add_column("hospitalizations", sa.Column("discharged_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE hospitalizations SET discharged_at = clinically_discharged_at")
    op.drop_constraint(
        op.f("fk_hospitalizations_facility_id_facilities"),
        "hospitalizations",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_hospitalizations_episode_id_episodes"),
        "hospitalizations",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_hospitalizations_facility_id"), table_name="hospitalizations")
    op.drop_index(op.f("ix_hospitalizations_episode_id"), table_name="hospitalizations")
    op.drop_column("hospitalizations", "closed_at")
    op.drop_column("hospitalizations", "administratively_discharged_at")
    op.drop_column("hospitalizations", "physically_departed_at")
    op.drop_column("hospitalizations", "clinically_discharged_at")
    op.drop_column("hospitalizations", "admission_type")
    op.drop_column("hospitalizations", "facility_id")
    op.drop_column("hospitalizations", "episode_id")

    op.drop_constraint(op.f("fk_episodes_facility_id_facilities"), "episodes", type_="foreignkey")
    op.drop_index(op.f("ix_episodes_facility_id"), table_name="episodes")
    op.drop_column("episodes", "facility_id")

    postgresql.ENUM(name="care_team_role").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot remove enum values: the new hospitalization_status values stay.
