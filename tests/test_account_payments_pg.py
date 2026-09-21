"""La caja de la internación: qué paga el paciente y qué traba el alta administrativa."""

from decimal import Decimal

import pytest

from app.core.exceptions import DomainError
from app.models.account import PaymentMethod, PaymentStatus, ResponsibleParty
from app.schemas.domain import AdministrativeDischargeCreate
from app.schemas.workflow import (
    ChargeItemCreate,
    ClinicalDischargeCreate,
    PaymentCreate,
    PaymentVoidCreate,
    PhysicalDepartureCreate,
)
from app.services.account import AccountService
from app.services.bed_assignment import BedAssignmentService
from app.services.hospitalization import HospitalizationService
from tests.conftest import requires_postgres, run_db
from tests.factories import build_scenario, hospitalization_from_admission

pytestmark = requires_postgres


async def stay_with_patient_charge(factory, scenario, amount: str = "3000.00"):
    """Internación de un paciente particular, con la cama liberada y un cargo a su cargo."""

    async with factory() as session:
        hospitalization_id = await hospitalization_from_admission(session, scenario)
    async with factory() as session:
        await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
    async with factory() as session:
        await AccountService(session).add_charge_item(
            hospitalization_id,
            ChargeItemCreate(
                category="HOSPITALIZATION_DAY",
                description="Día de internación",
                quantity=1,
                unit_price=amount,
            ),
        )
    async with factory() as session:
        await HospitalizationService(session).clinical_discharge(
            hospitalization_id,
            ClinicalDischargeCreate(),
        )
    async with factory() as session:
        await HospitalizationService(session).physical_departure(
            hospitalization_id,
            PhysicalDepartureCreate(),
        )
    return hospitalization_id


def test_a_private_patient_charge_is_his_to_pay():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await stay_with_patient_charge(factory, scenario)
        async with factory() as check:
            account = await AccountService(check).for_hospitalization(hospitalization_id)
            return (
                [item.responsible_party for item in account.charge_items],
                AccountService.patient_total(account),
                AccountService.payer_total(account),
                AccountService.patient_balance(account),
            )

    parties, patient_total, payer_total, balance = run_db(case)

    assert parties == [ResponsibleParty.PATIENT]
    assert patient_total == Decimal("3000.00")
    assert payer_total == Decimal(0)
    assert balance == Decimal("3000.00")


def test_the_administrative_discharge_is_blocked_while_the_patient_owes_money():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await stay_with_patient_charge(factory, scenario)
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await HospitalizationService(session).administrative_discharge(
                    hospitalization_id,
                    AdministrativeDischargeCreate(),
                )
            return error.value.status_code, error.value.message

    status_code, message = run_db(case)

    assert status_code == 409
    assert "cancele su saldo" in message
    assert "3000.00" in message


def test_the_discharge_goes_through_once_the_patient_pays():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await stay_with_patient_charge(factory, scenario)
        # Dos cobros parciales: mientras quede saldo el alta sigue trabada.
        async with factory() as session:
            await AccountService(session).register_payment(
                hospitalization_id,
                PaymentCreate(amount="1000.00", method=PaymentMethod.CASH),
            )
        async with factory() as session:
            with pytest.raises(DomainError):
                await HospitalizationService(session).administrative_discharge(
                    hospitalization_id,
                    AdministrativeDischargeCreate(),
                )
        async with factory() as session:
            await AccountService(session).register_payment(
                hospitalization_id,
                PaymentCreate(amount="2000.00", method=PaymentMethod.DEBIT_CARD),
            )
        async with factory() as session:
            hospitalization = await HospitalizationService(session).administrative_discharge(
                hospitalization_id,
                AdministrativeDischargeCreate(),
            )
            status = hospitalization.status
        async with factory() as check:
            account = await AccountService(check).for_hospitalization(hospitalization_id)
            return status, AccountService.paid_total(account), AccountService.patient_balance(
                account
            )

    status, paid, balance = run_db(case)

    assert status.value == "ADMINISTRATIVELY_DISCHARGED"
    assert paid == Decimal("3000.00")
    assert balance == Decimal(0)


def test_a_payment_cannot_exceed_what_the_patient_owes():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await stay_with_patient_charge(factory, scenario)
        async with factory() as session:
            with pytest.raises(DomainError) as error:
                await AccountService(session).register_payment(
                    hospitalization_id,
                    PaymentCreate(amount="3500.00", method=PaymentMethod.CASH),
                )
            return error.value.status_code

    assert run_db(case) == 409


def test_a_voided_payment_leaves_the_balance_owed_again():
    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        hospitalization_id = await stay_with_patient_charge(factory, scenario)
        async with factory() as session:
            payment = await AccountService(session).register_payment(
                hospitalization_id,
                PaymentCreate(amount="3000.00", method=PaymentMethod.CASH),
            )
            payment_id = payment.id
        async with factory() as session:
            await AccountService(session).void_payment(
                hospitalization_id,
                payment_id,
                PaymentVoidCreate(reason="Cupón rechazado", actor="caja"),
            )
        async with factory() as check:
            account = await AccountService(check).for_hospitalization(hospitalization_id)
            payment = account.payments[0]
            return payment.status, AccountService.patient_balance(account)

    status, balance = run_db(case)

    assert status == PaymentStatus.VOID
    assert balance == Decimal("3000.00")


def test_what_the_payer_owes_does_not_block_the_discharge():
    """Lo que se le factura al financiador se cobra después, por convenio."""

    async def case(factory):
        async with factory() as setup:
            scenario = await build_scenario(setup)
        async with factory() as session:
            hospitalization_id = await hospitalization_from_admission(session, scenario)
        async with factory() as session:
            await BedAssignmentService(session).assign(hospitalization_id, scenario.bed_ids[0])
        async with factory() as session:
            await AccountService(session).add_charge_item(
                hospitalization_id,
                ChargeItemCreate(
                    category="HOSPITALIZATION_DAY",
                    description="Día de internación",
                    quantity=1,
                    unit_price="3000.00",
                    responsible_party=ResponsibleParty.PAYER,
                ),
            )
        async with factory() as session:
            await HospitalizationService(session).clinical_discharge(
                hospitalization_id,
                ClinicalDischargeCreate(),
            )
        async with factory() as session:
            await HospitalizationService(session).physical_departure(
                hospitalization_id,
                PhysicalDepartureCreate(),
            )
        async with factory() as session:
            hospitalization = await HospitalizationService(session).administrative_discharge(
                hospitalization_id,
                AdministrativeDischargeCreate(),
            )
            return hospitalization.status.value

    assert run_db(case) == "ADMINISTRATIVELY_DISCHARGED"
