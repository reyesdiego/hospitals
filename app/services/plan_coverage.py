"""Cartilla de un plan: qué prácticas cubre y en qué condiciones.

The catalog says what a practice *is*; this says what a plan does with it — whether it is
covered at all, how long the affiliate has to wait before using it, what they pay out of
pocket and whether the payer wants to authorize it first.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DomainError, integrity_conflict
from app.models.coverage import HealthPlan, PatientCoverage
from app.models.practice import (
    HealthPlanPractice,
    MedicalPractice,
    PlanCoverageStatus,
    PracticeChapter,
)
from app.schemas.practice import (
    HealthPlanPracticeBulkCreate,
    HealthPlanPracticeCreate,
    HealthPlanPracticeUpdate,
)

BLOCKING_STATUSES = {
    PlanCoverageStatus.NOT_LISTED,
    PlanCoverageStatus.NOT_COVERED,
    PlanCoverageStatus.WAITING_PERIOD,
}


def effective_waiting_period(entry: HealthPlanPractice, practice: MedicalPractice) -> int:
    """La carencia que rige: la que pactó el plan, o la de la práctica si no pactó ninguna."""

    if entry.waiting_period_days is None:
        return practice.default_waiting_period_days
    return entry.waiting_period_days


@dataclass(frozen=True)
class PlanCoverageCheck:
    """Lo que la cartilla del plan dice sobre una práctica en una fecha."""

    status: PlanCoverageStatus
    copayment_amount: Decimal = Decimal(0)
    requires_authorization: bool = False
    waiting_period_days: int = 0
    available_from: date | None = None
    health_plan_id: uuid.UUID | None = None
    plan_practice_id: uuid.UUID | None = None
    message: str | None = None

    @property
    def blocked(self) -> bool:
        return self.status in BLOCKING_STATUSES


async def evaluate_coverage(
    session: AsyncSession,
    coverage: PatientCoverage | None,
    practice: MedicalPractice,
    *,
    on: date,
) -> PlanCoverageCheck:
    """Resuelve la cartilla del plan de ``coverage`` para ``practice``.

    Sin plan no hay cartilla, y un plan sin cartilla cargada no bloquea nada: una lista vacía
    significa que nadie la cargó, no que el plan no cubra nada. Recién cuando el plan tiene
    cartilla la lista pasa a ser cerrada y lo que no figura queda afuera.
    """

    if not coverage:
        return PlanCoverageCheck(status=PlanCoverageStatus.NO_COVERAGE)
    if not coverage.health_plan_id:
        # Cobertura cargada a mano: sin plan del catálogo no hay cartilla contra qué mirar.
        return PlanCoverageCheck(
            status=PlanCoverageStatus.NO_PLAN,
            message=(
                f"La cobertura de {coverage.payer_name} no está vinculada a un plan del "
                "catálogo: no se aplican cartilla, carencias ni copagos"
            ),
        )

    plan_id = coverage.health_plan_id
    entry = await session.scalar(
        select(HealthPlanPractice).where(
            HealthPlanPractice.health_plan_id == plan_id,
            HealthPlanPractice.practice_id == practice.id,
        )
    )
    if entry is None:
        loaded = await session.scalar(
            select(func.count())
            .select_from(HealthPlanPractice)
            .where(HealthPlanPractice.health_plan_id == plan_id)
        )
        if not loaded:
            return PlanCoverageCheck(
                status=PlanCoverageStatus.NO_CARTILLA, health_plan_id=plan_id
            )
        return PlanCoverageCheck(
            status=PlanCoverageStatus.NOT_LISTED,
            health_plan_id=plan_id,
            message=(
                f"La práctica {practice.code} no está en la cartilla del plan de "
                f"{coverage.payer_name}"
            ),
        )

    # La carencia del plan pisa a la de la práctica; sin carencia propia rige la del
    # nomenclador.
    waiting_period_days = effective_waiting_period(entry, practice)
    common = {
        "copayment_amount": entry.copayment_amount,
        "requires_authorization": entry.requires_authorization,
        "waiting_period_days": waiting_period_days,
        "health_plan_id": plan_id,
        "plan_practice_id": entry.id,
    }

    if not entry.is_covered:
        return PlanCoverageCheck(
            status=PlanCoverageStatus.NOT_COVERED,
            message=(
                f"El plan de {coverage.payer_name} no cubre la práctica {practice.code}"
            ),
            **common,
        )

    # La carencia corre desde el alta de la cobertura del afiliado; sin fecha de alta no hay
    # desde cuándo contarla, así que se da por cumplida.
    available_from = (
        coverage.valid_from + timedelta(days=waiting_period_days)
        if coverage.valid_from and waiting_period_days
        else None
    )
    if available_from and on < available_from:
        return PlanCoverageCheck(
            status=PlanCoverageStatus.WAITING_PERIOD,
            available_from=available_from,
            message=(
                f"La práctica {practice.code} está en carencia hasta el "
                f"{available_from.isoformat()} ({waiting_period_days} días desde el alta "
                "de la cobertura)"
            ),
            **common,
        )

    # Con carencia configurada pero sin fecha de alta no hay desde cuándo contarla: se deja
    # pasar, pero se dice, que es distinto de no tener carencia.
    unverifiable = None
    if waiting_period_days > 0 and coverage.valid_from is None:
        unverifiable = (
            f"La cobertura de {coverage.payer_name} no tiene fecha de alta: la carencia de "
            f"{waiting_period_days} días no puede verificarse"
        )
    return PlanCoverageCheck(
        status=PlanCoverageStatus.COVERED,
        available_from=available_from,
        message=unverifiable,
        **common,
    )


class HealthPlanPracticeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_practices(
        self,
        health_plan_id: uuid.UUID,
        *,
        chapter: PracticeChapter | None = None,
        search: str | None = None,
        only_covered: bool = False,
    ) -> list[HealthPlanPractice]:
        await self._require_plan(health_plan_id)
        stmt = (
            select(HealthPlanPractice)
            .join(MedicalPractice, MedicalPractice.id == HealthPlanPractice.practice_id)
            .options(selectinload(HealthPlanPractice.practice))
            .where(HealthPlanPractice.health_plan_id == health_plan_id)
            .order_by(MedicalPractice.nomenclador, MedicalPractice.code)
        )
        if chapter:
            stmt = stmt.where(MedicalPractice.chapter == chapter)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(MedicalPractice.code.ilike(pattern), MedicalPractice.name.ilike(pattern))
            )
        if only_covered:
            stmt = stmt.where(HealthPlanPractice.is_covered.is_(True))
        return list((await self.session.scalars(stmt)).all())

    async def get(
        self,
        health_plan_id: uuid.UUID,
        plan_practice_id: uuid.UUID,
    ) -> HealthPlanPractice:
        # Con ``session.get`` el ``selectinload`` se pierde cuando la fila ya está en la
        # sesión, y la práctica termina cargándose sola fuera del contexto async.
        entry = await self.session.scalar(
            select(HealthPlanPractice)
            .options(selectinload(HealthPlanPractice.practice))
            .where(HealthPlanPractice.id == plan_practice_id)
        )
        if not entry or entry.health_plan_id != health_plan_id:
            raise DomainError("La práctica no está en la cartilla del plan", 404)
        return entry

    async def link(
        self,
        health_plan_id: uuid.UUID,
        payload: HealthPlanPracticeCreate,
    ) -> HealthPlanPractice:
        async with (
            integrity_conflict(self.session, "La práctica ya está en la cartilla del plan"),
            self.session.begin(),
        ):
            await self._require_plan(health_plan_id)
            await self._require_practice(payload.practice_id)
            entry = HealthPlanPractice(health_plan_id=health_plan_id, **payload.model_dump())
            self.session.add(entry)
            await self.session.flush()
            return await self.get(health_plan_id, entry.id)

    async def link_many(
        self,
        health_plan_id: uuid.UUID,
        payload: HealthPlanPracticeBulkCreate,
    ) -> tuple[list[HealthPlanPractice], list[uuid.UUID]]:
        """Las prácticas que ya están en la cartilla se informan como omitidas en lugar de
        pisar las condiciones que alguien ya negoció."""

        async with self.session.begin():
            await self._require_plan(health_plan_id)
            requested = list(dict.fromkeys(payload.practice_ids))
            known = set(
                (
                    await self.session.scalars(
                        select(MedicalPractice.id).where(MedicalPractice.id.in_(requested))
                    )
                ).all()
            )
            missing = [practice_id for practice_id in requested if practice_id not in known]
            if missing:
                raise DomainError("Práctica inexistente", 404)

            already = set(
                (
                    await self.session.scalars(
                        select(HealthPlanPractice.practice_id).where(
                            HealthPlanPractice.health_plan_id == health_plan_id,
                            HealthPlanPractice.practice_id.in_(requested),
                        )
                    )
                ).all()
            )
            conditions = payload.model_dump(exclude={"practice_ids"})
            created = [
                HealthPlanPractice(
                    health_plan_id=health_plan_id, practice_id=practice_id, **conditions
                )
                for practice_id in requested
                if practice_id not in already
            ]
            self.session.add_all(created)
            await self.session.flush()
            created_ids = [entry.id for entry in created]

        entries = list(
            (
                await self.session.scalars(
                    select(HealthPlanPractice)
                    .options(selectinload(HealthPlanPractice.practice))
                    .where(HealthPlanPractice.id.in_(created_ids))
                )
            ).all()
            if created_ids
            else []
        )
        return entries, [practice_id for practice_id in requested if practice_id in already]

    async def update(
        self,
        health_plan_id: uuid.UUID,
        plan_practice_id: uuid.UUID,
        payload: HealthPlanPracticeUpdate,
    ) -> HealthPlanPractice:
        async with self.session.begin():
            entry = await self.get(health_plan_id, plan_practice_id)
            for field, value in payload.model_dump().items():
                setattr(entry, field, value)
            await self.session.flush()
            return entry

    async def unlink(self, health_plan_id: uuid.UUID, plan_practice_id: uuid.UUID) -> None:
        """Sacar la práctica de la cartilla. Para dejar constancia de que el plan no la cubre,
        marcarla como no cubierta en lugar de borrarla."""

        async with self.session.begin():
            entry = await self.get(health_plan_id, plan_practice_id)
            await self.session.delete(entry)

    async def _require_plan(self, health_plan_id: uuid.UUID) -> HealthPlan:
        plan = await self.session.get(HealthPlan, health_plan_id)
        if not plan:
            raise DomainError("Plan inexistente", 404)
        return plan

    async def _require_practice(self, practice_id: uuid.UUID) -> MedicalPractice:
        practice = await self.session.get(MedicalPractice, practice_id)
        if not practice:
            raise DomainError("Práctica inexistente", 404)
        return practice
