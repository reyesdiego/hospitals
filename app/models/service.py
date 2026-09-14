from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Service(UUIDMixin, TimestampMixin, Base):
    __tablename__="services"
    name: Mapped[str]=mapped_column(String(150))
    code: Mapped[str]=mapped_column(String(30), unique=True)
