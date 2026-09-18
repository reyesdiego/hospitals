"""Import surface used by Alembic so every model is registered in ``Base.metadata``."""

from app.models import *
from app.models.base import Base

__all__ = ["Base"]
