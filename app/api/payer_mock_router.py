"""API mock del financiador: valida el código de autorización que trae el afiliado."""

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.schemas.payer_mock import PayerAuthorizationRead, PayerAuthorizationRequest
from app.services.payer_mock import PayerAuthorizationMock

router = APIRouter(tags=["payer-mock"])


@router.post("/payer-mock/authorizations", response_model=PayerAuthorizationRead)
async def verify_payer_authorization(payload: PayerAuthorizationRequest, session: DbSession):
    """Simula la respuesta del financiador al código de autorización de 3 dígitos.

    Contesta si la práctica queda habilitada, con qué copago la cubre la cartilla del plan
    y, cuando no la autoriza, cuánto sale hacerla en forma particular.
    """

    return await PayerAuthorizationMock(session).verify(payload)
