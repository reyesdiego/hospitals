import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AccountStatus(str, enum.Enum):
    OPEN = "OPEN"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ChargeItemStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    VOID = "VOID"


class ChargeCategory(str, enum.Enum):
    HOSPITALIZATION_DAY = "HOSPITALIZATION_DAY"
    INTENSIVE_CARE_DAY = "INTENSIVE_CARE_DAY"
    MEDICATION = "MEDICATION"
    LABORATORY = "LABORATORY"
    IMAGING = "IMAGING"
    PROCEDURE = "PROCEDURE"
    SUPPLY = "SUPPLY"
    PROFESSIONAL_FEE = "PROFESSIONAL_FEE"
    OTHER = "OTHER"


class Account(UUIDMixin, TimestampMixin, Base):
    """Financial account of a hospitalization. Financial closure is independent from
    clinical discharge."""

    __tablename__ = "accounts"

    hospitalization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitalizations.id", ondelete="RESTRICT"), unique=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    coverage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patient_coverages.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status"), default=AccountStatus.OPEN
    )
    currency: Mapped[str] = mapped_column(String(3), default="ARS", server_default="ARS")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ready_for_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    charge_items: Mapped[list["ChargeItem"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class ChargeItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "charge_items"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    # A charge may come from a nomenclated practice; the code is snapshotted so the
    # account keeps reading the same way if the catalog entry changes later.
    practice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("medical_practices.id", ondelete="RESTRICT"), index=True
    )
    practice_code: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[ChargeCategory] = mapped_column(Enum(ChargeCategory, name="charge_category"))
    description: Mapped[str] = mapped_column(String(250))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(1))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    charged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)
    # A charge is never deleted: it is voided and stops adding to the total.
    status: Mapped[ChargeItemStatus] = mapped_column(
        Enum(ChargeItemStatus, name="charge_item_status"),
        default=ChargeItemStatus.ACTIVE,
        server_default=ChargeItemStatus.ACTIVE.value,
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[str | None] = mapped_column(String(150))
    void_reason: Mapped[str | None] = mapped_column(String(500))

    account: Mapped[Account] = relationship(back_populates="charge_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="non_negative_unit_price"),
    )
