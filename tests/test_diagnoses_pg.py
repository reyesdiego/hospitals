"""Catálogo CIE-10: carga del archivo y mantenimiento de los códigos."""

import pytest

from app.core.exceptions import DomainError
from app.db.seeds.diagnoses import read_catalog
from app.models.diagnosis import DiagnosisLevel
from app.schemas.diagnosis import DiagnosisCodeCreate, DiagnosisCodeUpdate
from app.services.diagnosis import DiagnosisService
from tests.conftest import requires_postgres, run_db

pytestmark = requires_postgres

#: Una rama entera del árbol, para probar sin cargar las catorce mil filas.
BRANCH = [
    ("J00-J99", "Enfermedades del sistema respiratorio", DiagnosisLevel.CHAPTER, None),
    ("J09-J18", "Influenza y neumonía", DiagnosisLevel.BLOCK, "J00-J99"),
    ("J15", "Neumonía bacteriana, no clasificada en otra parte", DiagnosisLevel.CATEGORY, "J09-J18"),
    ("J159", "Neumonía bacteriana, no especificada", DiagnosisLevel.SUBCATEGORY, "J15"),
]


async def load_branch(session) -> dict:
    service = DiagnosisService(session)
    created = {}
    for code, description, level, parent in BRANCH:
        created[code] = await service.create(
            DiagnosisCodeCreate(
                code=code,
                description=description,
                level=level,
                parent_code=parent,
                chapter_code="J00-J99",
            )
        )
    return created


def test_the_catalog_file_is_a_complete_tree():
    """El archivo que se versiona: sin huérfanos y con los capítulos en la raíz."""

    rows = read_catalog()
    codes = {row["code"] for row in rows}

    assert len(rows) == len(codes)
    assert len(rows) > 14000
    assert all(row["parent_code"] in codes for row in rows if row["parent_code"])
    chapters = [row for row in rows if row["level"] == DiagnosisLevel.CHAPTER]
    assert len(chapters) == 21
    assert all(row["parent_code"] is None for row in chapters)


def test_a_diagnosis_is_created_under_its_parent():
    async def case(factory):
        async with factory() as session:
            created = await load_branch(session)
            entry = created["J159"]
            return entry.code, entry.level, entry.parent_code, entry.chapter_code

    code, level, parent, chapter = run_db(case)

    assert code == "J159"
    assert level == DiagnosisLevel.SUBCATEGORY
    assert parent == "J15"
    assert chapter == "J00-J99"


def test_the_code_is_unique_and_the_parent_has_to_exist():
    async def case(factory):
        async with factory() as session:
            await load_branch(session)
            service = DiagnosisService(session)
            with pytest.raises(DomainError) as duplicated:
                await service.create(
                    DiagnosisCodeCreate(code="J159", description="Repetido", parent_code="J15")
                )
            with pytest.raises(DomainError) as orphan:
                await service.create(
                    DiagnosisCodeCreate(code="J158", description="Huérfano", parent_code="Z99")
                )
            return duplicated.value.status_code, orphan.value.status_code

    assert run_db(case) == (409, 404)


def test_the_catalog_is_searched_by_code_and_by_text():
    async def case(factory):
        async with factory() as session:
            await load_branch(session)
            service = DiagnosisService(session)
            by_code = await service.list_codes(search="j15")
            by_text = await service.list_codes(search="neumonía")
            codifiable = await service.list_codes(only_codifiable=True)
            chapter = await service.list_codes(level=DiagnosisLevel.CHAPTER)
            children = await service.list_codes(parent_code="J15")
            return (
                [entry.code for entry in by_code],
                [entry.code for entry in by_text],
                [entry.code for entry in codifiable],
                [entry.code for entry in chapter],
                [entry.code for entry in children],
            )

    by_code, by_text, codifiable, chapter, children = run_db(case)

    assert by_code == ["J15", "J159"]
    assert by_text == ["J09-J18", "J15", "J159"]
    # Capítulos y grupos ordenan la lista, no se le asientan a un paciente.
    assert codifiable == ["J15", "J159"]
    assert chapter == ["J00-J99"]
    assert children == ["J159"]


def test_a_code_that_is_no_longer_used_is_deactivated():
    async def case(factory):
        async with factory() as session:
            created = await load_branch(session)
            service = DiagnosisService(session)
            updated = await service.update(
                created["J159"].id,
                DiagnosisCodeUpdate(
                    description="Neumonía bacteriana, no especificada",
                    level=DiagnosisLevel.SUBCATEGORY,
                    parent_code="J15",
                    chapter_code="J00-J99",
                    is_active=False,
                    notes="Reemplazado por el código propio de la institución",
                ),
            )
            active = await service.list_codes(only_active=True)
            return updated.is_active, [entry.code for entry in active]

    is_active, active = run_db(case)

    assert is_active is False
    assert "J159" not in active


def test_a_diagnosis_with_children_is_not_deleted():
    async def case(factory):
        async with factory() as session:
            created = await load_branch(session)
            # Los ids, antes de que el rollback del borrado fallido expire los objetos.
            category_id, leaf_id = created["J15"].id, created["J159"].id
            service = DiagnosisService(session)
            with pytest.raises(DomainError) as error:
                await service.delete(category_id)
            # La hoja sí, que es el código cargado por error.
            await service.delete(leaf_id)
            remaining = await service.list_codes()
            return error.value.status_code, [entry.code for entry in remaining]

    status_code, remaining = run_db(case)

    assert status_code == 409
    assert remaining == ["J00-J99", "J09-J18", "J15"]
