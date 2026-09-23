"""Lo que la admisión toma del paciente cuando se presenta: contacto y consentimientos."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.admission import Admission, AdmissionConsent
from app.schemas.domain import AdmissionArrivalCreate, AdmissionConsentCreate


def add_consents(
    session: AsyncSession,
    admission: Admission,
    consents: list[AdmissionConsentCreate],
    at: datetime,
) -> None:
    for consent in consents:
        session.add(
            AdmissionConsent(
                admission_id=admission.id,
                consent_type=consent.consent_type,
                signed_by=consent.signed_by,
                signed_at=consent.signed_at or at,
                notes=consent.notes,
            )
        )


def record_arrival(
    session: AsyncSession,
    admission: Admission,
    arrival: AdmissionArrivalCreate | None,
    at: datetime,
) -> None:
    """Completa la admisión con lo que se toma al llegar el paciente.

    Una orden médica programada se registra sin contacto porque el paciente todavía no
    llegó; cuando se lo interna en una cama el contacto deja de ser opcional. El que ya
    estaba cargado se conserva salvo que se informe otro.
    """

    if arrival is not None:
        name = (arrival.responsible_contact_name or "").strip()
        phone = (arrival.responsible_contact_phone or "").strip()
        relationship = (arrival.responsible_contact_relationship or "").strip()
        if name:
            admission.responsible_contact_name = name
        if phone:
            admission.responsible_contact_phone = phone
        if relationship:
            admission.responsible_contact_relationship = relationship
        add_consents(session, admission, arrival.consents, at)

    if not (admission.responsible_contact_name and admission.responsible_contact_phone):
        raise DomainError(
            "Falta el contacto responsable: nombre y teléfono, antes de internar al paciente",
            422,
        )
