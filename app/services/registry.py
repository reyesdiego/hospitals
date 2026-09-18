"""Patient identity registry and coverage catalog."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, integrity_conflict
from app.models.coverage import HealthPlan, PatientCoverage, Payer
from app.models.patient import Patient, PatientContact, PatientIdentifier, PatientIdentifierType
from app.schemas.domain import PatientCoverageCreate
from app.schemas.workflow import (
    HealthPlanCreate,
    PatientContactCreate,
    PatientIdentifierCreate,
    PayerCreate,
)


async def build_coverage(
    session: AsyncSession,
    patient_id: uuid.UUID,
    payload: PatientCoverageCreate,
) -> PatientCoverage:
    """Create a coverage inside the caller's transaction, snapshotting payer/plan names."""

    payer_name = payload.payer_name
    plan_name = payload.plan_name
    payer: Payer | None = None
    if payload.payer_id:
        payer = await session.get(Payer, payload.payer_id)
        if not payer:
            raise DomainError("Financiador inexistente", 404)
        payer_name = payer.name
    if payload.health_plan_id:
        plan = await session.get(HealthPlan, payload.health_plan_id)
        if not plan:
            raise DomainError("Plan inexistente", 404)
        if payload.payer_id and plan.payer_id != payload.payer_id:
            raise DomainError("El plan no pertenece al financiador informado", 422)
        if payer is None:
            payer = await session.get(Payer, plan.payer_id)
            payer_name = payer.name if payer else payer_name
        plan_name = plan.name
    if not payer_name:
        raise DomainError("Informe payer_id o payer_name", 422)
    if payload.valid_from and payload.valid_until and payload.valid_until < payload.valid_from:
        raise DomainError("La vigencia de la cobertura es inválida", 422)

    coverage = PatientCoverage(
        patient_id=patient_id,
        payer_id=payload.payer_id or (payer.id if payer else None),
        health_plan_id=payload.health_plan_id,
        payer_name=payer_name,
        plan_name=plan_name,
        member_number=payload.member_number,
        authorization_required=payload.authorization_required,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        status=payload.status,
    )
    session.add(coverage)
    return coverage


class PatientRegistryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_identifier(
        self,
        patient_id: uuid.UUID,
        payload: PatientIdentifierCreate,
    ) -> PatientIdentifier:
        async with (
            integrity_conflict(self.session, "El identificador ya existe"),
            self.session.begin(),
        ):
            await self._require_patient(patient_id)
            identifier = PatientIdentifier(
                patient_id=patient_id,
                identifier_type=payload.identifier_type,
                value=payload.value,
                issuer=payload.issuer,
                is_primary=payload.is_primary,
            )
            self.session.add(identifier)
            await self.session.flush()
            return identifier

    async def list_identifiers(self, patient_id: uuid.UUID) -> list[PatientIdentifier]:
        await self._require_patient(patient_id)
        return list(
            (
                await self.session.scalars(
                    select(PatientIdentifier)
                    .where(PatientIdentifier.patient_id == patient_id)
                    .order_by(PatientIdentifier.is_primary.desc(), PatientIdentifier.created_at)
                )
            ).all()
        )

    async def search_patients(
        self,
        *,
        value: str,
        identifier_type: PatientIdentifierType | None = None,
    ) -> list[tuple[Patient, str]]:
        """Look for existing patients before creating a new one, to avoid duplicates."""

        conditions = [PatientIdentifier.value == value]
        if identifier_type:
            conditions.append(PatientIdentifier.identifier_type == identifier_type)
        by_identifier = (
            await self.session.execute(
                select(Patient, PatientIdentifier.identifier_type)
                .join(PatientIdentifier, PatientIdentifier.patient_id == Patient.id)
                .where(*conditions)
            )
        ).all()
        matches = {
            patient.id: (patient, f"identifier:{found_type.value}")
            for patient, found_type in by_identifier
        }

        by_document = (
            await self.session.scalars(
                select(Patient).where(
                    or_(Patient.document_number == value, Patient.document_number == value.strip())
                )
            )
        ).all()
        for patient in by_document:
            matches.setdefault(patient.id, (patient, "document_number"))
        return list(matches.values())

    async def add_contact(
        self,
        patient_id: uuid.UUID,
        payload: PatientContactCreate,
    ) -> PatientContact:
        async with self.session.begin():
            await self._require_patient(patient_id)
            contact = PatientContact(
                patient_id=patient_id,
                full_name=payload.full_name,
                relationship_to_patient=payload.relationship_to_patient,
                phone=payload.phone,
                email=payload.email,
                is_primary=payload.is_primary,
            )
            self.session.add(contact)
            await self.session.flush()
            return contact

    async def list_contacts(self, patient_id: uuid.UUID) -> list[PatientContact]:
        await self._require_patient(patient_id)
        return list(
            (
                await self.session.scalars(
                    select(PatientContact)
                    .where(PatientContact.patient_id == patient_id)
                    .order_by(PatientContact.is_primary.desc(), PatientContact.created_at)
                )
            ).all()
        )

    async def _require_patient(self, patient_id: uuid.UUID) -> Patient:
        patient = await self.session.get(Patient, patient_id)
        if not patient:
            raise DomainError("Paciente inexistente", 404)
        return patient


class CoverageService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_payers(self) -> list[Payer]:
        return list((await self.session.scalars(select(Payer).order_by(Payer.name))).all())

    async def create_payer(self, payload: PayerCreate) -> Payer:
        async with (
            integrity_conflict(self.session, "Código de financiador duplicado"),
            self.session.begin(),
        ):
            payer = Payer(**payload.model_dump())
            self.session.add(payer)
            await self.session.flush()
            return payer

    async def list_health_plans(self, payer_id: uuid.UUID) -> list[HealthPlan]:
        await self._require_payer(payer_id)
        return list(
            (
                await self.session.scalars(
                    select(HealthPlan)
                    .where(HealthPlan.payer_id == payer_id)
                    .order_by(HealthPlan.name)
                )
            ).all()
        )

    async def create_health_plan(
        self,
        payer_id: uuid.UUID,
        payload: HealthPlanCreate,
    ) -> HealthPlan:
        async with (
            integrity_conflict(self.session, "Código de plan duplicado para el financiador"),
            self.session.begin(),
        ):
            await self._require_payer(payer_id)
            plan = HealthPlan(payer_id=payer_id, **payload.model_dump())
            self.session.add(plan)
            await self.session.flush()
            return plan

    async def list_coverages(self, patient_id: uuid.UUID) -> list[PatientCoverage]:
        if not await self.session.get(Patient, patient_id):
            raise DomainError("Paciente inexistente", 404)
        return list(
            (
                await self.session.scalars(
                    select(PatientCoverage)
                    .where(PatientCoverage.patient_id == patient_id)
                    .order_by(PatientCoverage.created_at.desc())
                )
            ).all()
        )

    async def create_coverage(
        self,
        patient_id: uuid.UUID,
        payload: PatientCoverageCreate,
    ) -> PatientCoverage:
        async with self.session.begin():
            if not await self.session.get(Patient, patient_id):
                raise DomainError("Paciente inexistente", 404)
            coverage = await build_coverage(self.session, patient_id, payload)
            await self.session.flush()
            return coverage

    async def _require_payer(self, payer_id: uuid.UUID) -> Payer:
        payer = await self.session.get(Payer, payer_id)
        if not payer:
            raise DomainError("Financiador inexistente", 404)
        return payer
