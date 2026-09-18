"""Append-only audit trail for the admission/hospitalization/bed lifecycle."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import HospitalizationEvent, HospitalizationEventType


def record_event(
    session: AsyncSession,
    event_type: HospitalizationEventType,
    *,
    hospitalization_id: uuid.UUID | None = None,
    admission_id: uuid.UUID | None = None,
    bed_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    actor: str | None = None,
    occurred_at: datetime | None = None,
    details: dict[str, Any] | None = None,
) -> HospitalizationEvent:
    """Add an event to the current transaction; the caller owns the commit."""

    event = HospitalizationEvent(
        event_type=event_type,
        hospitalization_id=hospitalization_id,
        admission_id=admission_id,
        bed_id=bed_id,
        patient_id=patient_id,
        occurred_at=occurred_at or datetime.now(UTC),
        actor=actor,
        details=details,
    )
    session.add(event)
    return event


async def list_events(
    session: AsyncSession,
    hospitalization_id: uuid.UUID,
) -> list[HospitalizationEvent]:
    return list(
        (
            await session.scalars(
                select(HospitalizationEvent)
                .where(HospitalizationEvent.hospitalization_id == hospitalization_id)
                .order_by(HospitalizationEvent.occurred_at, HospitalizationEvent.created_at)
            )
        ).all()
    )
