import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CareTeamRole(str, enum.Enum):
    ATTENDING_PHYSICIAN = "ATTENDING_PHYSICIAN"
    SPECIALIST = "SPECIALIST"
    RESIDENT = "RESIDENT"
    NURSE = "NURSE"
    OTHER = "OTHER"


class CareTeam(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "care_teams"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), unique=True
    )

    members: Mapped[list["CareTeamMember"]] = relationship(
        back_populates="care_team",
        cascade="all, delete-orphan",
    )


class CareTeamMember(UUIDMixin, TimestampMixin, Base):
    """A practitioner taking part in the care team. ``practitioner`` is a Professional,
    which is a clinical concept and not an application user."""

    __tablename__ = "care_team_members"

    care_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("care_teams.id", ondelete="CASCADE"), index=True
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("professionals.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[CareTeamRole] = mapped_column(Enum(CareTeamRole, name="care_team_role"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(500))

    care_team: Mapped[CareTeam] = relationship(back_populates="members")

    __table_args__ = (
        Index(
            "uq_active_care_team_member_role",
            "care_team_id",
            "practitioner_id",
            "role",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index(
            "uq_active_attending_physician",
            "care_team_id",
            unique=True,
            postgresql_where=text("role = 'ATTENDING_PHYSICIAN' AND ended_at IS NULL"),
        ),
    )
