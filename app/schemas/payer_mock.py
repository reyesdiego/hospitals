"""Schemas del API mock de autorizaciones del financiador."""

import enum
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class PayerAuthorizationResult(str, enum.Enum):
    """Qué contestó el financiador al código que trajo el afiliado."""

    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"  # el código existe y el financiador no autoriza la práctica
    INVALID_CODE = "INVALID_CODE"  # no tiene el formato de 3 dígitos
    UNKNOWN_CODE = "UNKNOWN_CODE"  # el financiador no lo reconoce
    NOT_COVERED = "NOT_COVERED"  # la cartilla del plan excluye la práctica


class PayerAuthorizationRequest(BaseModel):
    """Lo que la admisión le manda al financiador para validar el código."""

    health_plan_id: uuid.UUID
    #: Código de 3 dígitos que trae el afiliado. Se valida acá, no en el esquema, para
    #: poder contestar "código inválido" como respuesta del financiador y no como error.
    authorization_code: str = Field(max_length=20)
    #: La práctica que se quiere hacer. Sin ella el financiador solo valida el código.
    practice_id: uuid.UUID | None = None
    member_number: str | None = Field(default=None, max_length=80)
    on: date | None = None


class PayerAuthorizationRead(BaseModel):
    """Respuesta del financiador, con la plata que queda a cargo del paciente."""

    authorized: bool
    result: PayerAuthorizationResult
    authorization_code: str
    #: Número que devuelve el financiador cuando autoriza; es el que se guarda en la admisión.
    authorization_number: str | None
    valid_until: date | None
    message: str
    payer_id: uuid.UUID
    payer_name: str
    health_plan_id: uuid.UUID
    plan_name: str
    practice_id: uuid.UUID | None
    practice_code: str | None
    practice_name: str | None
    #: ``None`` cuando no se informó práctica, o cuando el plan no tiene cartilla cargada.
    plan_covers_practice: bool | None
    #: Copago de la cartilla: lo que el paciente paga aun con la práctica autorizada.
    copayment_amount: Decimal
    #: Valor particular de la práctica, para ofrecerla sin cobertura si no se autoriza.
    private_amount: Decimal | None
    #: Lo que el paciente tiene que pagar: el copago si está autorizada, el valor
    #: particular si no lo está.
    patient_due: Decimal
    currency: str
