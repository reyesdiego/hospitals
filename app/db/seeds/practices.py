"""Load the practice catalog into ``medical_practices``.

The rows live in :data:`CATALOG_PATH` as a CSV with one nomenclador entry per line, so the
catalog can be reviewed and diffed as data instead of as code. Loading is idempotent: the
pair (nomenclador, code) is the identity of an entry, an unknown code is inserted and a
known one is updated, and nothing is ever deleted — a code that is retired is deactivated
by hand, because hospitalizations already point at it.

The nomenclador publishes *units*, not money. Tariffs are therefore optional here: with
``--unit-value`` the institutional tariff (the one with no payer behind it) is created for
every practice whose units can be priced, which is enough to bill a demo account.

    python -m app.db.seeds.practices
    python -m app.db.seeds.practices --unit-value 850 --valid-from 2026-01-01
"""

import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory, engine
from app.models.practice import (
    MedicalPractice,
    MedicalPracticeTariff,
    Nomenclador,
    PracticeChapter,
    PracticeSetting,
    PracticeType,
)

CATALOG_PATH = Path(__file__).with_name("nomenclador.csv")
CENTS = Decimal("0.01")

UNIT_FIELDS = (
    "galeno_units",
    "expense_units",
    "anesthesia_units",
    "biochemical_units",
    "radiology_units",
)
FLAGS = ("requires_authorization", "requires_consent")


@dataclass(frozen=True)
class LoadReport:
    inserted: int = 0
    updated: int = 0
    tariffs_created: int = 0
    tariffs_skipped: int = 0

    def __str__(self) -> str:
        lines = [f"prácticas: {self.inserted} nuevas, {self.updated} actualizadas"]
        if self.tariffs_created or self.tariffs_skipped:
            lines.append(
                f"aranceles institucionales: {self.tariffs_created} creados, "
                f"{self.tariffs_skipped} omitidos (sin unidades o ya vigentes)"
            )
        return "\n".join(lines)


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def read_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    """Parse the CSV into the keyword arguments of :class:`MedicalPractice`.

    Anything the enums do not accept fails here, before touching the database, so a typo in
    the data file is a parse error and not half a catalog.
    """
    rows: list[dict] = []
    seen: set[tuple[Nomenclador, str]] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for line, raw in enumerate(csv.DictReader(handle), start=2):
            code = (raw["code"] or "").strip()
            name = (raw["name"] or "").strip()
            if not code or not name:
                raise ValueError(f"{path.name}:{line}: falta el código o el nombre")
            try:
                entry = {
                    "nomenclador": Nomenclador(raw["nomenclador"].strip()),
                    "code": code,
                    "name": name,
                    "chapter": PracticeChapter(raw["chapter"].strip()),
                    "practice_type": PracticeType(raw["practice_type"].strip()),
                    "setting": PracticeSetting(raw["setting"].strip()),
                    "description": _text(raw.get("description")),
                }
            except ValueError as exc:
                raise ValueError(f"{path.name}:{line}: {exc}") from exc
            for field in UNIT_FIELDS:
                units = Decimal((raw[field] or "0").strip() or "0")
                if units < 0:
                    raise ValueError(f"{path.name}:{line}: {field} no puede ser negativo")
                entry[field] = units
            for field in FLAGS:
                entry[field] = (raw[field] or "").strip().lower() == "true"
            waiting = (raw.get("default_waiting_period_days") or "0").strip() or "0"
            if not waiting.isdigit():
                raise ValueError(f"{path.name}:{line}: la carencia debe ser un número de días")
            entry["default_waiting_period_days"] = int(waiting)

            identity = (entry["nomenclador"], entry["code"])
            if identity in seen:
                raise ValueError(f"{path.name}:{line}: código repetido {entry['code']}")
            seen.add(identity)
            rows.append(entry)
    return rows


async def load_catalog(
    session: AsyncSession,
    *,
    rows: list[dict] | None = None,
    unit_value: Decimal | None = None,
    valid_from: date | None = None,
) -> LoadReport:
    rows = read_catalog() if rows is None else rows
    existing = {
        (practice.nomenclador, practice.code): practice
        for practice in (await session.scalars(select(MedicalPractice))).all()
    }

    inserted = updated = 0
    practices: list[MedicalPractice] = []
    for entry in rows:
        practice = existing.get((entry["nomenclador"], entry["code"]))
        if practice is None:
            practice = MedicalPractice(**entry)
            session.add(practice)
            inserted += 1
        else:
            # The catalog is the source of truth for what the nomenclador says; ``is_active``
            # and the validity dates are the institution's decision and are left alone.
            for field, value in entry.items():
                setattr(practice, field, value)
            updated += 1
        practices.append(practice)
    await session.flush()

    created = skipped = 0
    if unit_value is not None:
        created, skipped = await _load_institutional_tariffs(
            session,
            practices,
            unit_value=unit_value,
            valid_from=valid_from or datetime.now(UTC).date(),
        )
    await session.commit()
    return LoadReport(inserted, updated, created, skipped)


async def _load_institutional_tariffs(
    session: AsyncSession,
    practices: list[MedicalPractice],
    *,
    unit_value: Decimal,
    valid_from: date,
) -> tuple[int, int]:
    """Price the units of each practice at ``unit_value``.

    Honorarios are the galeno, anesthesia and biochemical units; gastos the expense and
    radiology ones. The value of the unit is not stored: the amounts are the agreement, and
    a single ``unit_value`` would make the API re-derive them from the galeno units alone.
    Practices with no units (the ``PROPIO`` modules, billed as a closed amount) are skipped
    — their price is negotiated, not computed.
    """
    priced = {
        tariff.practice_id
        for tariff in (
            await session.scalars(
                select(MedicalPracticeTariff).where(
                    MedicalPracticeTariff.payer_id.is_(None),
                    MedicalPracticeTariff.health_plan_id.is_(None),
                    MedicalPracticeTariff.valid_from == valid_from,
                )
            )
        ).all()
    }

    created = skipped = 0
    for practice in practices:
        fee = _money(
            (practice.galeno_units + practice.anesthesia_units + practice.biochemical_units)
            * unit_value
        )
        expense = _money((practice.expense_units + practice.radiology_units) * unit_value)
        if fee + expense <= 0 or practice.id in priced:
            skipped += 1
            continue
        session.add(
            MedicalPracticeTariff(
                practice_id=practice.id,
                professional_fee=fee,
                expense_amount=expense,
                total_amount=fee + expense,
                valid_from=valid_from,
                notes=f"Arancel institucional sembrado a ${unit_value} la unidad",
            )
        )
        created += 1
    await session.flush()
    return created, skipped


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Carga el nomenclador de prácticas")
    parser.add_argument(
        "--unit-value",
        type=Decimal,
        help="Valor de la unidad para sembrar además el arancel institucional",
    )
    parser.add_argument(
        "--valid-from",
        type=date.fromisoformat,
        help="Vigencia de los aranceles sembrados (por defecto, hoy)",
    )
    args = parser.parse_args(argv)

    async with SessionFactory() as session:
        report = await load_catalog(
            session, unit_value=args.unit_value, valid_from=args.valid_from
        )
    await engine.dispose()
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
