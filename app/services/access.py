"""Qué se puede tocar de una internación según en qué punto de su vida está.

Antes de que el paciente llegue —orden médica programada con la cama reservada— no hay a
quién indicarle nada: la internación no admite nada clínico, cargos, ni cambios de servicio
o de equipo, tampoco de un administrador. Solo se gestiona la cama y la orden.

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


def require_patient_arrived(hospitalization: Hospitalization) -> None:
    if hospitalization.status == HospitalizationStatus.AWAITING_ARRIVAL:
        raise DomainError(
            "El paciente todavía no ingresó: la internación está programada y solo tiene la "
            "cama reservada. Se habilita cuando se confirma su ingreso en la cama",
            409,
        )


def require_editable(
    session: AsyncSession,
    hospitalization: Hospitalization,
    user: RequestUser,
    *,
    action: str,
) -> None:
    """Dentro de la transacción del llamador: corta si no corresponde, y si un administrador
    pasa por encima del alta médica, lo registra."""

    require_patient_arrived(hospitalization)
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
