"""Schemas del informe estadístico."""

from datetime import date

from pydantic import BaseModel

from app.models.diagnosis import DiagnosisRole, DiagnosisStage


class MorbidityRowRead(BaseModel):
    #: Código CIE-10 o código de capítulo, según cómo se haya agrupado.
    key: str
    description: str
    episodes: int
    patients: int
    deaths: int
    #: Estadía promedio en días; vacía cuando ninguna internación tiene fecha de ingreso.
    average_stay_days: float | None
    mortality_rate: float


class MorbidityReportRead(BaseModel):
    from_date: date | None
    to_date: date | None
    stage: DiagnosisStage
    role: DiagnosisRole | None
    group_by: str
    total_episodes: int
    #: Egresos del período sin diagnóstico codificado: no entran en las filas.
    uncoded_episodes: int
    rows: list[MorbidityRowRead]
