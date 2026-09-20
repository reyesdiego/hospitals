"""Qué se puede tocar de una internación según en qué punto de su vida está.

Con el alta médica dada, la internación deja de recibir cambios: lo que se cargue después
no lo vio el médico que firmó el alta. Un administrador puede hacerlo igual —hay errores que
aparecen después, y un resultado de laboratorio que llega tarde hay que poder cargarlo— pero
queda asentado en el historial de la internación.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.core.users import RequestUser
from app.models.audit import HospitalizationEventType
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.services.audit import record_event

#: Con el alta médica dada la internación queda cerrada a cambios, y sigue así después.
POST_DISCHARGE_STATUSES = {
    HospitalizationStatus.CLINICALLY_DISCHARGED,
    HospitalizationStatus.ADMINISTRATIVELY_DISCHARGED,
    HospitalizationStatus.CLOSED,
}


def require_editable(
    session: AsyncSession,
    hospitalization: Hospitalization,
    user: RequestUser,
    *,
    action: str,
) -> None:
    """Dentro de la transacción del llamador: corta si no corresponde, y si un administrador
    pasa por encima del alta médica, lo registra."""

    if hospitalization.status not in POST_DISCHARGE_STATUSES:
        return
    if not user.is_admin:
        raise DomainError(
            "La internación tiene alta médica: solo un administrador puede modificarla",
            403,
        )
    record_event(
        session,
        HospitalizationEventType.POST_DISCHARGE_CHANGE,
        hospitalization_id=hospitalization.id,
        patient_id=hospitalization.patient_id,
        actor=user.name,
        details={"action": action, "status": hospitalization.status.value},
    )
