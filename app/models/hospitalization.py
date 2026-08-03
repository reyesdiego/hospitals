import enum, uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin
class HospitalizationStatus(str, enum.Enum):
    PENDING_BED="PENDING_BED"; IN_PROGRESS="IN_PROGRESS"; CLINICALLY_DISCHARGED="CLINICALLY_DISCHARGED"; CLOSED="CLOSED"; CANCELLED="CANCELLED"
class Hospitalization(UUIDMixin, TimestampMixin, Base):
    __tablename__="hospitalizations"
    patient_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), index=True)
    status: Mapped[HospitalizationStatus]=mapped_column(Enum(HospitalizationStatus,name="hospitalization_status"), default=HospitalizationStatus.PENDING_BED)
    admission_reason: Mapped[str]=mapped_column(String(500))
    admitted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    discharged_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
