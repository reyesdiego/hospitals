"""Mock del API de autorizaciones del financiador.

La admisión le pasa a la prestadora el código de autorización de 3 dígitos que trae el
afiliado y la prestadora contesta si la práctica está habilitada. Mientras no exista la
integración real, este módulo hace de esa prestadora: no guarda nada y contesta siempre lo
mismo para el mismo código, para que el circuito de admisión se pueda probar y demostrar.

Reglas del mock, en orden:

1. el código tiene que ser de 3 dígitos (``INVALID_CODE``);
2. ``000`` es el código que la prestadora no reconoce (``UNKNOWN_CODE``);
3. si la cartilla del plan excluye la práctica, no hay código que la habilite
   (``NOT_COVERED``);
4. último dígito impar: la prestadora rechaza la autorización (``REJECTED``);
5. último dígito par: autorizada.

Lo que sale de la cartilla —el copago— y lo que sale del nomenclador —el valor particular—
son datos reales del sistema: lo único simulado es la respuesta de la prestadora.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.coverage import HealthPlan, Payer
from app.models.practice import HealthPlanPractice, MedicalPractice
from app.schemas.payer_mock import (
    PayerAuthorizationRead,
    PayerAuthorizationRequest,
    PayerAuthorizationResult,
)
from app.services.practice import MedicalPracticeService

#: Cuánto vale la autorización que devuelve la prestadora.
AUTHORIZATION_VALIDITY_DAYS = 30

#: Código que la prestadora usa para "no figura en el padrón".
UNKNOWN_AUTHORIZATION_CODE = "000"


class PayerAuthorizationMock:
    """La prestadora simulada: valida un código contra la cartilla del plan."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def verify(self, payload: PayerAuthorizationRequest) -> PayerAuthorizationRead:
        plan = await self.session.get(HealthPlan, payload.health_plan_id)
        if not plan:
            raise DomainError("Plan inexistente", 404)
        payer = await self.session.get(Payer, plan.payer_id)
        if not payer:
            raise DomainError("Financiador inexistente", 404)

        practice: MedicalPractice | None = None
        entry: HealthPlanPractice | None = None
        if payload.practice_id:
            practice = await self.session.get(MedicalPractice, payload.practice_id)
            if not practice:
                raise DomainError("Práctica inexistente", 404)
            entry = await self.session.scalar(
                select(HealthPlanPractice).where(
                    HealthPlanPractice.health_plan_id == plan.id,
                    HealthPlanPractice.practice_id == practice.id,
                )
            )

        on = payload.on or datetime.now(UTC).date()
        code = payload.authorization_code.strip()
        result, message = self._evaluate(code, payer=payer, practice=practice, entry=entry)
        authorized = result is PayerAuthorizationResult.AUTHORIZED

        # El copago es plata del afiliado y se paga igual con la práctica autorizada; el
        # valor particular es lo que se le cobra si la cobertura no se hace cargo.
        copayment = entry.copayment_amount if entry and entry.is_covered else Decimal(0)
        private_amount, currency = await self._private_price(practice, on=on)

        patient_due = copayment if authorized else (private_amount or Decimal(0))
        return PayerAuthorizationRead(
            authorized=authorized,
            result=result,
            authorization_code=code,
            authorization_number=self._authorization_number(payer, code, on)
            if authorized
            else None,
            valid_until=on + timedelta(days=AUTHORIZATION_VALIDITY_DAYS) if authorized else None,
            message=message,
            payer_id=payer.id,
            payer_name=payer.name,
            health_plan_id=plan.id,
            plan_name=plan.name,
            practice_id=practice.id if practice else None,
            practice_code=practice.code if practice else None,
            practice_name=practice.name if practice else None,
            plan_covers_practice=entry.is_covered if entry else None,
            copayment_amount=copayment,
            private_amount=private_amount,
            patient_due=patient_due,
            currency=currency,
        )

    def _evaluate(
        self,
        code: str,
        *,
        payer: Payer,
        practice: MedicalPractice | None,
        entry: HealthPlanPractice | None,
    ) -> tuple[PayerAuthorizationResult, str]:
        if len(code) != 3 or not code.isdigit():
            return (
                PayerAuthorizationResult.INVALID_CODE,
                "El código de autorización tiene que ser de 3 dígitos",
            )
        if code == UNKNOWN_AUTHORIZATION_CODE:
            return (
                PayerAuthorizationResult.UNKNOWN_CODE,
                f"{payer.name} no reconoce el código {code}",
            )
        if entry is not None and not entry.is_covered and practice is not None:
            return (
                PayerAuthorizationResult.NOT_COVERED,
                f"El plan de {payer.name} no cubre la práctica {practice.code}",
            )
        if int(code[-1]) % 2:
            practica = f" la práctica {practice.code}" if practice else ""
            return (
                PayerAuthorizationResult.REJECTED,
                f"{payer.name} no autoriza{practica} con el código {code}",
            )
        return (
            PayerAuthorizationResult.AUTHORIZED,
            f"{payer.name} autorizó el código {code}",
        )

    async def _private_price(
        self,
        practice: MedicalPractice | None,
        *,
        on: date,
    ) -> tuple[Decimal | None, str]:
        """Valor institucional de la práctica: el que se le cobra al paciente particular."""

        if not practice:
            return None, "ARS"
        try:
            tariff = await MedicalPracticeService(self.session).effective_tariff(
                practice.id, on=on
            )
        except DomainError:
            # Sin valor cargado no se puede ofrecer un precio: la admisión lo muestra así.
            return None, "ARS"
        return tariff.total_amount, tariff.currency

    def _authorization_number(self, payer: Payer, code: str, on: date) -> str:
        return f"{payer.code}-{on:%Y%m%d}-{code}"
