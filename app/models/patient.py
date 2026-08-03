from datetime import date
from sqlalchemy import Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin

class Patient(UUIDMixin, TimestampMixin, Base):
    __tablename__="patients"
    __table_args__=(UniqueConstraint("document_type","document_number",name="uq_patients_document"),)
    first_name: Mapped[str]=mapped_column(String(100))
    last_name: Mapped[str]=mapped_column(String(100))
    document_type: Mapped[str]=mapped_column(String(30))
    document_number: Mapped[str]=mapped_column(String(50))
    birth_date: Mapped[date|None]=mapped_column(Date)
