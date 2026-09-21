"""Pasar la frecuencia escrita a mano al esquema estructurado.

Las indicaciones cargadas antes de que existiera el esquema guardan la frecuencia como
texto —"cada 8 horas", "08:00 y 20:00", "a demanda"— y por eso quedaron todas como *a
demanda*: sin esquema no hay horarios que calcular ni tomas que se venzan.

Este script lee ese texto y, cuando lo entiende, completa el esquema. Lo que no entiende
lo deja como está y lo informa: es preferible una indicación sin horarios a una con
horarios que nadie indicó.

Por defecto no escribe nada; hay que pedirlo con ``--apply``.

    python -m app.db.maintenance.treatment_schedules            # qué cambiaría
    python -m app.db.maintenance.treatment_schedules --apply
"""

import argparse
import asyncio
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory, engine
from app.models.treatment import HospitalizationTreatment, ScheduleKind
from app.services.medication_schedule import frequency_label

#: Cuántas veces por día dice el texto, en palabras.
TIMES_PER_DAY = {
    "una": 1,
    "1": 1,
    "dos": 2,
    "2": 2,
    "tres": 3,
    "3": 3,
    "cuatro": 4,
    "4": 4,
    "seis": 6,
    "6": 6,
}

AS_NEEDED_WORDS = ("a demanda", "demanda", "sos", "prn", "s/n", "si dolor", "si precisa")
CONTINUOUS_WORDS = ("continuo", "continua", "permanente", "goteo", "infusion")
ONCE_WORDS = ("unica vez", "unica dosis", "una sola vez", "monodosis", "stat", "por unica")


@dataclass(frozen=True)
class Schedule:
    kind: ScheduleKind
    interval_hours: int | None = None
    times_of_day: tuple[time, ...] | None = None

    @property
    def label(self) -> str:
        return frequency_label(
            self.kind,
            interval_hours=self.interval_hours,
            times_of_day=list(self.times_of_day) if self.times_of_day else None,
        )


def _normalize(text: str) -> str:
    """Sin acentos y en minúsculas: "cada 8 horas" y "Cada 8 Horas" son lo mismo."""

    stripped = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(char for char in stripped if not unicodedata.combining(char))


def parse_frequency(text: str | None) -> Schedule | None:
    """El esquema que describe ``text``, o ``None`` si no se entiende.

    Se prefiere no entender a suponer: una indicación mal interpretada genera horarios
    falsos, y enfermería termina dando de más o marcando vencido lo que no lo está.
    """

    if not text or not text.strip():
        return None
    value = _normalize(text)

    if any(word in value for word in ONCE_WORDS):
        return Schedule(ScheduleKind.ONCE)
    if any(word in value for word in CONTINUOUS_WORDS):
        return Schedule(ScheduleKind.CONTINUOUS)
    if any(word in value for word in AS_NEEDED_WORDS):
        return Schedule(ScheduleKind.AS_NEEDED)

    # Horarios del día: "08:00 y 20:00", "8:00, 14:00, 20:00".
    clock = re.findall(r"\b(\d{1,2}):(\d{2})\b", value)
    if clock:
        moments = sorted(
            {
                time(int(hour), int(minute))
                for hour, minute in clock
                if int(hour) < 24 and int(minute) < 60
            }
        )
        if moments:
            return Schedule(ScheduleKind.TIMES, times_of_day=tuple(moments))

    # Intervalo: "cada 8 horas", "c/8 hs", "cada 12 h".
    interval = re.search(r"(?:cada|c/)\s*(\d{1,3})\s*(?:h|hs|hr|hrs|horas?)\b", value)
    if interval:
        hours = int(interval.group(1))
        if 1 <= hours <= 168:
            return Schedule(ScheduleKind.INTERVAL, interval_hours=hours)

    # Veces por día: "dos veces por dia", "3 veces al dia".
    per_day = re.search(r"\b(\w+)\s*(?:veces|vez)\s*(?:por|al)\s*dia\b", value)
    if per_day:
        times = TIMES_PER_DAY.get(per_day.group(1))
        if times:
            return Schedule(ScheduleKind.INTERVAL, interval_hours=24 // times)

    if re.search(r"\b(diario|diaria|por dia|cada dia|1 vez)\b", value):
        return Schedule(ScheduleKind.INTERVAL, interval_hours=24)

    return None


@dataclass
class Row:
    treatment_id: uuid.UUID
    description: str
    frequency: str | None
    schedule: Schedule | None

    @property
    def understood(self) -> bool:
        return self.schedule is not None


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)
    applied: bool = False

    @property
    def understood(self) -> list[Row]:
        return [row for row in self.rows if row.understood]

    @property
    def unknown(self) -> list[Row]:
        return [row for row in self.rows if not row.understood]

    def __str__(self) -> str:
        if not self.rows:
            return "No hay indicaciones sin esquema para migrar."
        verb = "quedaron" if self.applied else "quedarían"
        lines = [
            f"{len(self.understood)} de {len(self.rows)} indicaciones {verb} con esquema:"
        ]
        for row in self.understood[:20]:
            lines.append(
                f"  {row.description[:28]:<28} {str(row.frequency)[:20]:<20} "
                f"→ {row.schedule.label}"
            )
        if len(self.understood) > 20:
            lines.append(f"  ... y {len(self.understood) - 20} más")
        if self.unknown:
            lines.append(
                f"{len(self.unknown)} quedan a demanda porque su frecuencia no se entiende:"
            )
            for row in self.unknown[:10]:
                lines.append(f"  {row.description[:28]:<28} {row.frequency!r}")
            if len(self.unknown) > 10:
                lines.append(f"  ... y {len(self.unknown) - 10} más")
        if not self.applied:
            lines.append("Nada fue modificado: volvé a correrlo con --apply.")
        return "\n".join(lines)


async def migrate_schedules(session: AsyncSession, *, apply: bool = False) -> Report:
    """Completa el esquema de las indicaciones que quedaron sin uno.

    Solo mira las que están como *a demanda* sin datos cargados: una indicación que
    alguien ya configuró a mano no se toca.
    """

    candidates = list(
        (
            await session.scalars(
                select(HospitalizationTreatment).where(
                    HospitalizationTreatment.schedule_kind == ScheduleKind.AS_NEEDED,
                    HospitalizationTreatment.interval_hours.is_(None),
                    HospitalizationTreatment.times_of_day.is_(None),
                )
            )
        ).all()
    )
    report = Report(
        rows=[
            Row(
                treatment_id=treatment.id,
                description=treatment.description,
                frequency=treatment.frequency,
                schedule=parse_frequency(treatment.frequency),
            )
            for treatment in candidates
        ],
        applied=apply,
    )
    if not apply:
        return report

    by_id = {treatment.id: treatment for treatment in candidates}
    for row in report.understood:
        treatment = by_id[row.treatment_id]
        treatment.schedule_kind = row.schedule.kind
        treatment.interval_hours = row.schedule.interval_hours
        treatment.times_of_day = (
            list(row.schedule.times_of_day) if row.schedule.times_of_day else None
        )
        # El texto original se respeta: es lo que escribió quien indicó.
        treatment.frequency = treatment.frequency or row.schedule.label
    await session.commit()
    return report


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Pasa la frecuencia escrita a mano al esquema estructurado"
    )
    parser.add_argument("--apply", action="store_true", help="Escribir los cambios")
    args = parser.parse_args(argv)

    async with SessionFactory() as session:
        report = await migrate_schedules(session, apply=args.apply)
    await engine.dispose()
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
