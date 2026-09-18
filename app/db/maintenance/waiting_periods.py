"""Pasar carencias pactadas en la cartilla a la carencia de la práctica.

Las cartillas cargadas antes de que la carencia del plan fuera opcional guardan un valor
explícito, casi siempre ``0`` porque era el que venía por defecto. Ese ``0`` significa "este
plan pactó cero", así que no sigue a la práctica cuando su carencia cambia. Este script pasa
esas filas a la herencia (``waiting_period_days`` vacío).

Por defecto solo toca las que tienen ``0`` y no escribe nada: hay que pedirlo con ``--apply``.

    python -m app.db.maintenance.waiting_periods                      # qué cambiaría
    python -m app.db.maintenance.waiting_periods --apply
    python -m app.db.maintenance.waiting_periods --plan <uuid> --any --apply
"""

import argparse
import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import SessionFactory, engine
from app.models.coverage import HealthPlan
from app.models.practice import HealthPlanPractice


@dataclass
class Row:
    plan: str
    practice_code: str
    agreed: int
    inherited: int


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)
    applied: bool = False

    def __str__(self) -> str:
        if not self.rows:
            return "No hay carencias pactadas para pasar a herencia."
        changed = sum(1 for row in self.rows if row.agreed != row.inherited)
        verb = "pasaron" if self.applied else "pasarían"
        lines = [
            (
                f"{len(self.rows)} prácticas {verb} a la carencia de la práctica "
                f"({changed} cambian de valor):"
            )
        ]
        for row in self.rows[:20]:
            arrow = f"{row.agreed} → {row.inherited}"
            lines.append(f"  {row.plan:<20} {row.practice_code:<12} {arrow}")
        if len(self.rows) > 20:
            lines.append(f"  ... y {len(self.rows) - 20} más")
        if not self.applied:
            lines.append("Nada fue modificado: volvé a correrlo con --apply.")
        return "\n".join(lines)


async def inherit_waiting_periods(
    session: AsyncSession,
    *,
    health_plan_id: uuid.UUID | None = None,
    only_value: int | None = 0,
    apply: bool = False,
) -> Report:
    """``only_value`` en None toma cualquier carencia pactada; en 0, solo las que valen cero."""

    stmt = (
        select(HealthPlanPractice, HealthPlan.name)
        .join(HealthPlan, HealthPlan.id == HealthPlanPractice.health_plan_id)
        .options(selectinload(HealthPlanPractice.practice))
        .where(HealthPlanPractice.waiting_period_days.is_not(None))
        .order_by(HealthPlan.name)
    )
    if health_plan_id:
        if not await session.get(HealthPlan, health_plan_id):
            raise ValueError("Plan inexistente")
        stmt = stmt.where(HealthPlanPractice.health_plan_id == health_plan_id)
    if only_value is not None:
        stmt = stmt.where(HealthPlanPractice.waiting_period_days == only_value)

    found = (await session.execute(stmt)).all()
    report = Report(
        rows=[
            Row(
                plan=plan_name,
                practice_code=entry.practice.code,
                agreed=entry.waiting_period_days,
                inherited=entry.practice.default_waiting_period_days,
            )
            for entry, plan_name in found
        ],
        applied=apply,
    )
    if apply:
        for entry, _ in found:
            entry.waiting_period_days = None
        await session.commit()
    return report


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Pasa las carencias pactadas en la cartilla a la carencia de la práctica"
    )
    parser.add_argument("--plan", type=uuid.UUID, help="Limitar a un plan")
    parser.add_argument(
        "--any",
        action="store_true",
        help="Tomar cualquier carencia pactada, no solo las que valen 0",
    )
    parser.add_argument("--apply", action="store_true", help="Escribir los cambios")
    args = parser.parse_args(argv)

    async with SessionFactory() as session:
        report = await inherit_waiting_periods(
            session,
            health_plan_id=args.plan,
            only_value=None if args.any else 0,
            apply=args.apply,
        )
    await engine.dispose()
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
