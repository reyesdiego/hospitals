"""Informe estadístico de morbilidad: qué se atendió, contado por diagnóstico.

Es el informe que el hospital manda al ministerio y el que mira la dirección: cuántos
egresos hubo por cada diagnóstico del CIE-10, cuántos pacientes distintos, cuánto duró la
internación promedio y cuántos fallecieron. Se cuenta sobre los egresos —una internación
en curso todavía no tiene diagnóstico definitivo— y por el diagnóstico principal, que es
el que motivó la internación.

Los egresos sin diagnóstico codificado se informan aparte en lugar de desaparecer: un
informe que no dice lo que le falta se lee como si estuviera completo.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.diagnosis import (
    DiagnosisCode,
    DiagnosisLevel,
    DiagnosisRole,
    DiagnosisStage,
    HospitalizationDiagnosis,
)
from app.models.discharge import Discharge, DischargeType
from app.models.hospitalization import Hospitalization, HospitalizationServiceAssignment


class MorbidityGrouping:
    """Cómo se agrupan las filas del informe."""

    CODE = "CODE"
    CHAPTER = "CHAPTER"


@dataclass(frozen=True)
class MorbidityRow:
    key: str
    description: str
    episodes: int
    patients: int
    deaths: int
    average_stay_days: float | None

    @property
    def mortality_rate(self) -> float:
        return round(self.deaths / self.episodes * 100, 1) if self.episodes else 0.0


@dataclass(frozen=True)
class MorbidityReport:
    from_date: date | None
    to_date: date | None
    stage: DiagnosisStage
    role: DiagnosisRole | None
    group_by: str
    rows: list[MorbidityRow] = field(default_factory=list)
    #: Egresos del período sin diagnóstico codificado en el momento pedido.
    uncoded_episodes: int = 0

    @property
    def total_episodes(self) -> int:
        return sum(row.episodes for row in self.rows)


def _day_bounds(day: date, *, end: bool = False) -> datetime:
    """El período se pide en fechas locales; las altas se guardan en UTC."""

    zone = ZoneInfo(settings.timezone)
    moment = datetime.combine(day, time.min, tzinfo=zone)
    return moment + timedelta(days=1) if end else moment


def _discharged_scope(
    stmt: Select,
    *,
    from_date: date | None,
    to_date: date | None,
    service_id: uuid.UUID | None,
) -> Select:
    """Los egresos del período, opcionalmente los de un servicio."""

    stmt = stmt.where(Hospitalization.clinically_discharged_at.is_not(None))
    if from_date:
        stmt = stmt.where(Hospitalization.clinically_discharged_at >= _day_bounds(from_date))
    if to_date:
        stmt = stmt.where(
            Hospitalization.clinically_discharged_at < _day_bounds(to_date, end=True)
        )
    if service_id:
        stmt = stmt.where(
            select(HospitalizationServiceAssignment.id)
            .where(
                HospitalizationServiceAssignment.hospitalization_id == Hospitalization.id,
                HospitalizationServiceAssignment.service_id == service_id,
            )
            .exists()
        )
    return stmt


async def morbidity_report(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    service_id: uuid.UUID | None = None,
    stage: DiagnosisStage = DiagnosisStage.DISCHARGE,
    role: DiagnosisRole | None = DiagnosisRole.PRINCIPAL,
    group_by: str = MorbidityGrouping.CODE,
) -> MorbidityReport:
    stay_days = func.avg(
        func.extract(
            "epoch",
            Hospitalization.clinically_discharged_at - Hospitalization.admitted_at,
        )
        / 86400
    )
    deaths = func.count(Discharge.id).filter(
        Discharge.discharge_type == DischargeType.DECEASED
    )

    if group_by == MorbidityGrouping.CHAPTER:
        key, description = DiagnosisCode.chapter_code, DiagnosisCode.chapter_code
    else:
        key, description = HospitalizationDiagnosis.code, func.max(
            HospitalizationDiagnosis.description
        )

    stmt = (
        select(
            key.label("key"),
            description.label("description"),
            func.count(func.distinct(Hospitalization.id)).label("episodes"),
            func.count(func.distinct(Hospitalization.patient_id)).label("patients"),
            deaths.label("deaths"),
            stay_days.label("stay"),
        )
        .select_from(HospitalizationDiagnosis)
        .join(
            Hospitalization,
            Hospitalization.id == HospitalizationDiagnosis.hospitalization_id,
        )
        .join(
            DiagnosisCode,
            DiagnosisCode.id == HospitalizationDiagnosis.diagnosis_code_id,
        )
        .outerjoin(Discharge, Discharge.hospitalization_id == Hospitalization.id)
        .where(HospitalizationDiagnosis.stage == stage)
        .group_by(key)
        .order_by(func.count(func.distinct(Hospitalization.id)).desc(), key)
    )
    if role:
        stmt = stmt.where(HospitalizationDiagnosis.role == role)
    stmt = _discharged_scope(
        stmt,
        from_date=from_date,
        to_date=to_date,
        service_id=service_id,
    )
    rows = (await session.execute(stmt)).all()

    titles: dict[str, str] = {}
    if group_by == MorbidityGrouping.CHAPTER:
        titles = {
            code: text
            for code, text in (
                await session.execute(
                    select(DiagnosisCode.code, DiagnosisCode.description).where(
                        DiagnosisCode.level == DiagnosisLevel.CHAPTER
                    )
                )
            ).all()
        }

    # Los egresos que nadie codificó: se cuentan aparte para que el total cierre.
    uncoded = (
        _discharged_scope(
            select(func.count(func.distinct(Hospitalization.id))).select_from(Hospitalization),
            from_date=from_date,
            to_date=to_date,
            service_id=service_id,
        )
        .where(
            ~select(HospitalizationDiagnosis.id)
            .where(
                and_(
                    HospitalizationDiagnosis.hospitalization_id == Hospitalization.id,
                    HospitalizationDiagnosis.stage == stage,
                    *([HospitalizationDiagnosis.role == role] if role else []),
                )
            )
            .exists()
        )
    )

    return MorbidityReport(
        from_date=from_date,
        to_date=to_date,
        stage=stage,
        role=role,
        group_by=group_by,
        rows=[
            MorbidityRow(
                key=row.key or "-",
                description=titles.get(row.key, row.description or row.key or "-"),
                episodes=row.episodes,
                patients=row.patients,
                deaths=row.deaths,
                average_stay_days=round(float(row.stay), 1) if row.stay is not None else None,
            )
            for row in rows
        ],
        uncoded_episodes=await session.scalar(uncoded) or 0,
    )
