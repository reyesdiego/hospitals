"""Informes estadísticos."""

import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.api.dependencies import DbSession
from app.models.diagnosis import DiagnosisRole, DiagnosisStage
from app.schemas.report import MorbidityReportRead, MorbidityRowRead
from app.services.reports import MorbidityGrouping, morbidity_report

router = APIRouter(tags=["reports"])


@router.get("/reports/morbidity", response_model=MorbidityReportRead)
async def get_morbidity_report(
    session: DbSession,
    from_date: date | None = None,
    to_date: date | None = None,
    service_id: uuid.UUID | None = None,
    stage: DiagnosisStage = DiagnosisStage.DISCHARGE,
    role: DiagnosisRole | None = DiagnosisRole.PRINCIPAL,
    group_by: str = Query(
        default=MorbidityGrouping.CODE,
        pattern=f"^({MorbidityGrouping.CODE}|{MorbidityGrouping.CHAPTER})$",
    ),
):
    """Egresos por diagnóstico CIE-10, con pacientes, estadía promedio y fallecidos.

    Se cuenta sobre los egresos del período y, por omisión, por el diagnóstico principal
    de egreso. ``role`` vacío cuenta todos los diagnósticos, con lo que una internación
    puede aparecer en varias filas.
    """

    report = await morbidity_report(
        session,
        from_date=from_date,
        to_date=to_date,
        service_id=service_id,
        stage=stage,
        role=role,
        group_by=group_by,
    )
    return MorbidityReportRead(
        from_date=report.from_date,
        to_date=report.to_date,
        stage=report.stage,
        role=report.role,
        group_by=report.group_by,
        total_episodes=report.total_episodes,
        uncoded_episodes=report.uncoded_episodes,
        rows=[
            MorbidityRowRead(
                key=row.key,
                description=row.description,
                episodes=row.episodes,
                patients=row.patients,
                deaths=row.deaths,
                average_stay_days=row.average_stay_days,
                mortality_rate=row.mortality_rate,
            )
            for row in report.rows
        ],
    )
