"""Responsible-service history of a hospitalization."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import HospitalizationEventType
from app.models.hospitalization import Hospitalization, HospitalizationServiceAssignment
from app.services.audit import record_event


async def active_service_assignment(
    session: AsyncSession,
    hospitalization_id: uuid.UUID,
    *,
    lock: bool = False,
) -> HospitalizationServiceAssignment | None:
    stmt = select(HospitalizationServiceAssignment).where(
        HospitalizationServiceAssignment.hospitalization_id == hospitalization_id,
        HospitalizationServiceAssignment.ended_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def reassign_service(
    session: AsyncSession,
    hospitalization: Hospitalization,
    service_id: uuid.UUID,
    *,
    at: datetime,
    reason: str | None = None,
    assigned_by: str | None = None,
) -> HospitalizationServiceAssignment:
    """Close the current assignment and open a new one. History is never overwritten."""

    current = await active_service_assignment(session, hospitalization.id, lock=True)
    if current is not None:
        current.ended_at = at
    assignment = HospitalizationServiceAssignment(
        hospitalization_id=hospitalization.id,
        service_id=service_id,
        started_at=at,
        reason=reason,
        assigned_by=assigned_by,
    )
    session.add(assignment)
    record_event(
        session,
        HospitalizationEventType.SERVICE_ASSIGNED,
        hospitalization_id=hospitalization.id,
        patient_id=hospitalization.patient_id,
        actor=assigned_by,
        occurred_at=at,
        details={
            "service_id": str(service_id),
            "previous_service_id": str(current.service_id) if current else None,
            "reason": reason,
        },
    )
    return assignment
