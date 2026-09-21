"""Catálogo CIE-10: consulta y mantenimiento."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, integrity_conflict
from app.core.users import STAFF, RequestUser
from app.models.audit import HospitalizationEventType
from app.models.diagnosis import (
    CODIFIABLE_LEVELS,
    DiagnosisCode,
    DiagnosisLevel,
    DiagnosisRole,
    DiagnosisStage,
    HospitalizationDiagnosis,
)
from app.models.hospitalization import Hospitalization
from app.models.professional import Professional
from app.schemas.diagnosis import (
    DiagnosisCodeCreate,
    DiagnosisCodeUpdate,
    HospitalizationDiagnosisCreate,
    HospitalizationDiagnosisUpdate,
)
from app.services.access import require_editable
from app.services.audit import record_event

#: El catálogo tiene más de catorce mil códigos: se busca, no se lista entero.
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class DiagnosisService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_codes(
        self,
        *,
        search: str | None = None,
        chapter_code: str | None = None,
        parent_code: str | None = None,
        level: DiagnosisLevel | None = None,
        only_active: bool = False,
        only_codifiable: bool = False,
        limit: int = DEFAULT_LIMIT,
    ) -> list[DiagnosisCode]:
        """``search`` busca por código o por texto del diagnóstico."""

        stmt = select(DiagnosisCode).order_by(DiagnosisCode.code).limit(
            max(1, min(limit, MAX_LIMIT))
        )
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    DiagnosisCode.code.ilike(pattern),
                    DiagnosisCode.description.ilike(pattern),
                )
            )
        if chapter_code:
            stmt = stmt.where(DiagnosisCode.chapter_code == chapter_code)
        if parent_code:
            stmt = stmt.where(DiagnosisCode.parent_code == parent_code)
        if level:
            stmt = stmt.where(DiagnosisCode.level == level)
        if only_codifiable:
            stmt = stmt.where(DiagnosisCode.level.in_(CODIFIABLE_LEVELS))
        if only_active:
            stmt = stmt.where(DiagnosisCode.is_active.is_(True))
        return list((await self.session.scalars(stmt)).all())

    async def get(self, diagnosis_id: uuid.UUID) -> DiagnosisCode:
        code = await self.session.get(DiagnosisCode, diagnosis_id)
        if not code:
            raise DomainError("Diagnóstico inexistente", 404)
        return code

    async def get_by_code(self, code: str) -> DiagnosisCode:
        found = await self.session.scalar(
            select(DiagnosisCode).where(DiagnosisCode.code == code.strip())
        )
        if not found:
            raise DomainError("Diagnóstico inexistente", 404)
        return found

    async def create(self, payload: DiagnosisCodeCreate) -> DiagnosisCode:
        async with (
            integrity_conflict(self.session, "El código de diagnóstico ya existe"),
            self.session.begin(),
        ):
            data = payload.model_dump()
            data["code"] = data["code"].strip().upper()
            await self._require_parent(data["parent_code"], level=data["level"])
            entry = DiagnosisCode(**data)
            self.session.add(entry)
            await self.session.flush()
            return entry

    async def update(
        self,
        diagnosis_id: uuid.UUID,
        payload: DiagnosisCodeUpdate,
    ) -> DiagnosisCode:
        async with self.session.begin():
            entry = await self.get(diagnosis_id)
            data = payload.model_dump()
            if data["parent_code"] == entry.code:
                raise DomainError("Un diagnóstico no puede ser su propio padre", 422)
            await self._require_parent(data["parent_code"], level=data["level"])
            for field, value in data.items():
                setattr(entry, field, value)
            await self.session.flush()
            return entry

    async def delete(self, diagnosis_id: uuid.UUID) -> None:
        """Solo para un código cargado por error. Para sacar de circulación uno que ya se
        usó, desactivarlo: las historias siguen apuntando a él."""

        async with (
            integrity_conflict(
                self.session,
                "No se puede eliminar un diagnóstico con registros asociados",
            ),
            self.session.begin(),
        ):
            entry = await self.get(diagnosis_id)
            children = await self.session.scalar(
                select(func.count())
                .select_from(DiagnosisCode)
                .where(DiagnosisCode.parent_code == entry.code)
            )
            if children:
                raise DomainError(
                    f"El diagnóstico {entry.code} tiene {children} códigos que dependen de él",
                    409,
                )
            await self.session.delete(entry)

    async def _require_parent(self, parent_code: str | None, *, level: DiagnosisLevel) -> None:
        if parent_code is None:
            return
        exists = await self.session.scalar(
            select(DiagnosisCode.id).where(DiagnosisCode.code == parent_code)
        )
        if not exists:
            raise DomainError(f"El diagnóstico padre {parent_code} no existe", 404)
        if level == DiagnosisLevel.CHAPTER:
            raise DomainError("Un capítulo no cuelga de otro código", 422)


async def require_codifiable(session: AsyncSession, code: str) -> DiagnosisCode:
    """Al paciente se le asienta una categoría o una subcategoría: un capítulo del CIE-10
    no es un diagnóstico, y un código dado de baja no se usa más."""

    found = await session.scalar(
        select(DiagnosisCode).where(DiagnosisCode.code == code.strip().upper())
    )
    if not found:
        raise DomainError(f"El diagnóstico {code} no está en el catálogo CIE-10", 404)
    if found.level not in CODIFIABLE_LEVELS:
        raise DomainError(
            f"{found.code} es un {found.level.value.lower()} del CIE-10: elija un código "
            "de diagnóstico",
            422,
        )
    if not found.is_active:
        raise DomainError(f"El diagnóstico {found.code} no está vigente", 409)
    return found


async def record_diagnoses(
    session: AsyncSession,
    hospitalization: Hospitalization,
    payloads: list[HospitalizationDiagnosisCreate],
    *,
    stage: DiagnosisStage,
    user: RequestUser = STAFF,
    at: datetime | None = None,
) -> list[HospitalizationDiagnosis]:
    """Asienta diagnósticos dentro de la transacción del llamador.

    Es la puerta que usan la admisión —diagnósticos de ingreso— y el alta médica
    —diagnósticos de egreso—, que arman la internación en una sola transacción.
    """

    if not payloads:
        return []
    now = at or datetime.now(UTC)
    principals = [item for item in payloads if item.role == DiagnosisRole.PRINCIPAL]
    if len(principals) > 1:
        raise DomainError("Solo puede haber un diagnóstico principal", 422)
    if principals:
        await require_free_principal(
            session,
            hospitalization.id,
            role=DiagnosisRole.PRINCIPAL,
            stage=stage,
        )

    codes = [payload.code.strip().upper() for payload in payloads]
    if len(set(codes)) != len(codes):
        raise DomainError("El mismo diagnóstico está informado dos veces", 422)

    entries: list[HospitalizationDiagnosis] = []
    for payload in payloads:
        code = await require_codifiable(session, payload.code)
        if payload.diagnosed_by_id and not await session.get(
            Professional, payload.diagnosed_by_id
        ):
            raise DomainError("Profesional inexistente", 404)
        entry = HospitalizationDiagnosis(
            hospitalization_id=hospitalization.id,
            diagnosis_code_id=code.id,
            # Copia del catálogo: la clasificación se edita y la historia no cambia.
            code=code.code,
            description=code.description,
            role=payload.role,
            stage=stage,
            diagnosed_by_id=payload.diagnosed_by_id,
            recorded_by_user_id=user.id,
            recorded_by_user_name=user.name,
            diagnosed_at=payload.diagnosed_at or now,
            notes=payload.notes,
        )
        session.add(entry)
        record_event(
            session,
            HospitalizationEventType.DIAGNOSIS_RECORDED,
            hospitalization_id=hospitalization.id,
            patient_id=hospitalization.patient_id,
            actor=user.name,
            occurred_at=now,
            details={
                "code": code.code,
                "description": code.description,
                "role": payload.role.value,
                "stage": stage.value,
            },
        )
        entries.append(entry)
    await session.flush()
    return entries


async def require_free_principal(
    session: AsyncSession,
    hospitalization_id: uuid.UUID,
    *,
    role: DiagnosisRole,
    stage: DiagnosisStage,
) -> None:
    """Un solo diagnóstico principal por momento: es el que va a la estadística."""

    if role != DiagnosisRole.PRINCIPAL:
        return
    current = await session.scalar(
        select(HospitalizationDiagnosis.code).where(
            HospitalizationDiagnosis.hospitalization_id == hospitalization_id,
            HospitalizationDiagnosis.stage == stage,
            HospitalizationDiagnosis.role == DiagnosisRole.PRINCIPAL,
        )
    )
    if current:
        raise DomainError(
            f"La internación ya tiene a {current} como diagnóstico principal: cámbielo de "
            "rol antes de asentar otro",
            409,
        )


class HospitalizationDiagnosisService:
    """Los diagnósticos asentados en una internación.

    Con el alta médica dada la internación no recibe más cambios, salvo de un administrador:
    el diagnóstico es parte de lo que el médico firmó.
    """

    def __init__(self, session: AsyncSession, user: RequestUser = STAFF):
        self.session = session
        self.user = user

    async def list_for_hospitalization(
        self,
        hospitalization_id: uuid.UUID,
        *,
        stage: DiagnosisStage | None = None,
    ) -> list[HospitalizationDiagnosis]:
        await self._require_hospitalization(hospitalization_id)
        stmt = (
            select(HospitalizationDiagnosis)
            .where(HospitalizationDiagnosis.hospitalization_id == hospitalization_id)
            # Primero el principal, que es el que contesta "por qué está internado".
            .order_by(
                HospitalizationDiagnosis.stage,
                HospitalizationDiagnosis.role != DiagnosisRole.PRINCIPAL,
                HospitalizationDiagnosis.diagnosed_at,
            )
        )
        if stage:
            stmt = stmt.where(HospitalizationDiagnosis.stage == stage)
        return list((await self.session.scalars(stmt)).all())

    async def add(
        self,
        hospitalization_id: uuid.UUID,
        payload: HospitalizationDiagnosisCreate,
    ) -> HospitalizationDiagnosis:
        async with (
            integrity_conflict(
                self.session,
                "El diagnóstico ya está asentado en ese momento de la internación",
            ),
            self.session.begin(),
        ):
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Asentar un diagnóstico",
            )
            entries = await record_diagnoses(
                self.session,
                hospitalization,
                [payload],
                stage=payload.stage,
                user=self.user,
            )
            return entries[0]

    async def update(
        self,
        hospitalization_id: uuid.UUID,
        entry_id: uuid.UUID,
        payload: HospitalizationDiagnosisUpdate,
    ) -> HospitalizationDiagnosis:
        async with (
            integrity_conflict(
                self.session,
                "La internación ya tiene un diagnóstico principal en ese momento",
            ),
            self.session.begin(),
        ):
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Corregir un diagnóstico",
            )
            entry = await self._require_entry(hospitalization_id, entry_id)
            if payload.diagnosed_by_id and not await self.session.get(
                Professional, payload.diagnosed_by_id
            ):
                raise DomainError("Profesional inexistente", 404)
            if payload.role != entry.role:
                await require_free_principal(
                    self.session,
                    hospitalization_id,
                    role=payload.role,
                    stage=entry.stage,
                )
            entry.role = payload.role
            entry.diagnosed_by_id = payload.diagnosed_by_id
            entry.notes = payload.notes
            await self.session.flush()
            return entry

    async def remove(self, hospitalization_id: uuid.UUID, entry_id: uuid.UUID) -> None:
        """Un diagnóstico mal asentado se quita; el historial guarda que estuvo."""

        async with self.session.begin():
            hospitalization = await self._require_hospitalization(hospitalization_id)
            require_editable(
                self.session,
                hospitalization,
                self.user,
                action="Quitar un diagnóstico",
            )
            entry = await self._require_entry(hospitalization_id, entry_id)
            record_event(
                self.session,
                HospitalizationEventType.DIAGNOSIS_REMOVED,
                hospitalization_id=hospitalization_id,
                patient_id=hospitalization.patient_id,
                actor=self.user.name,
                details={"code": entry.code, "stage": entry.stage.value},
            )
            await self.session.delete(entry)

    async def _require_hospitalization(self, hospitalization_id: uuid.UUID) -> Hospitalization:
        hospitalization = await self.session.get(Hospitalization, hospitalization_id)
        if not hospitalization:
            raise DomainError("Internación inexistente", 404)
        return hospitalization

    async def _require_entry(
        self,
        hospitalization_id: uuid.UUID,
        entry_id: uuid.UUID,
    ) -> HospitalizationDiagnosis:
        entry = await self.session.get(HospitalizationDiagnosis, entry_id)
        if not entry or entry.hospitalization_id != hospitalization_id:
            raise DomainError("Diagnóstico inexistente en la internación", 404)
        return entry

