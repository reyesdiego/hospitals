"""Carga el catálogo CIE-10 en ``diagnosis_codes``.

Las filas viven en :data:`CATALOG_PATH` como CSV —código, descripción, nivel, padre y
capítulo— para que el catálogo se revise y se versione como datos y no como código. La
carga es idempotente: el código es la identidad, uno desconocido se inserta y uno conocido
se actualiza. Nada se borra: un código que se deja de usar se desactiva a mano, porque las
historias clínicas ya apuntan a él.

    python -m app.db.seeds.diagnoses
    python -m app.db.seeds.diagnoses --dry-run

Fuente: https://github.com/verasativa/CIE-10 (CIE-10 en español, icdcode.info + DEIS Chile).
"""

import argparse
import asyncio
import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory, engine
from app.models.diagnosis import DiagnosisCode, DiagnosisLevel

CATALOG_PATH = Path(__file__).with_name("cie10.csv")

#: De arriba hacia abajo: un hijo no puede insertarse antes que su padre.
LEVEL_ORDER = [
    DiagnosisLevel.CHAPTER,
    DiagnosisLevel.BLOCK,
    DiagnosisLevel.CATEGORY,
    DiagnosisLevel.SUBCATEGORY,
]


@dataclass(frozen=True)
class LoadReport:
    inserted: int = 0
    updated: int = 0

    def __str__(self) -> str:
        return f"diagnósticos CIE-10: {self.inserted} nuevos, {self.updated} actualizados"


def _text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def read_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    """Parsea el CSV y valida el árbol antes de tocar la base.

    Un padre que no está en el archivo es un error acá y no una fila huérfana en la tabla.
    """

    rows: list[dict] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for line, raw in enumerate(csv.DictReader(handle), start=2):
            code = (raw["code"] or "").strip().upper()
            description = " ".join((raw["description"] or "").split())
            if not code or not description:
                raise ValueError(f"{path.name}:{line}: falta el código o la descripción")
            if code in seen:
                raise ValueError(f"{path.name}:{line}: código repetido {code}")
            seen.add(code)
            try:
                level = DiagnosisLevel(raw["level"].strip())
            except ValueError as exc:
                raise ValueError(f"{path.name}:{line}: {exc}") from exc
            rows.append(
                {
                    "code": code,
                    "description": description,
                    "level": level,
                    "parent_code": _text(raw.get("parent_code")),
                    "chapter_code": _text(raw.get("chapter_code")),
                }
            )

    for entry in rows:
        parent = entry["parent_code"]
        if parent and parent not in seen:
            raise ValueError(f"{path.name}: {entry['code']} cuelga de {parent}, que no existe")
        if entry["level"] == DiagnosisLevel.CHAPTER and parent:
            raise ValueError(f"{path.name}: el capítulo {entry['code']} no puede tener padre")
    rows.sort(key=lambda entry: (LEVEL_ORDER.index(entry["level"]), entry["code"]))
    return rows


async def load_catalog(
    session: AsyncSession,
    *,
    rows: list[dict] | None = None,
) -> LoadReport:
    rows = read_catalog() if rows is None else rows
    existing = {
        code.code: code for code in (await session.scalars(select(DiagnosisCode))).all()
    }

    inserted = updated = 0
    # Nivel por nivel, de arriba hacia abajo: la tabla apunta a sí misma y el padre tiene
    # que estar escrito antes que el hijo.
    for level in LEVEL_ORDER:
        for entry in (row for row in rows if row["level"] == level):
            code = existing.get(entry["code"])
            if code is None:
                session.add(DiagnosisCode(**entry))
                inserted += 1
            else:
                # El CSV manda sobre lo que dice la clasificación; ``is_active`` y las
                # notas son decisión de la institución y no se pisan.
                for field, value in entry.items():
                    setattr(code, field, value)
                updated += 1
        await session.flush()
    await session.commit()
    return LoadReport(inserted, updated)


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="valida el archivo y no escribe en la base",
    )
    args = parser.parse_args(argv)

    rows = read_catalog()
    if args.dry_run:
        print(f"{len(rows)} diagnósticos listos para cargar desde {CATALOG_PATH.name}")
        return
    async with SessionFactory() as session:
        print(await load_catalog(session, rows=rows))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
