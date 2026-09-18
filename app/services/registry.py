"""Patient identity registry and coverage catalog."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, integrity_conflict
from app.models.account import Account
from app.models.admission import Admission
from app.models.authorization import Authorization
from app.models.coverage import HealthPlan, PatientCoverage, Payer
from app.models.patient import Patient, PatientContact, PatientIdentifier, PatientIdentifierType
from app.models.practice import MedicalPracticeTariff
from app.schemas.domain import PatientCoverageCreate, PatientCoverageUpdate
from app.schemas.workflow import (
    HealthPlanCreate,
    HealthPlanUpdate,
    PatientContactCreate,
    PatientIdentifierCreate,
    PayerCreate,
    PayerUpdate,
)


async def coverage_fields(
    session: AsyncSession,
    payload: PatientCoverageCreate | PatientCoverageUpdate,
) -> dict:
    """Resolve a coverage payload into column values, snapshotting payer/plan names.

    The payer and the plan are optional because a coverage can be loaded from the card the
    patient brings, before the payer exists in the catalog; what is never optional is the
    name, which is what the invoice and the authorization are issued against.
    """

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

    return {
        "payer_id": payload.payer_id or (payer.id if payer else None),
        "health_plan_id": payload.health_plan_id,
        "payer_name": payer_name,
        "plan_name": plan_name,
        "member_number": payload.member_number,
        "authorization_required": payload.authorization_required,
        "valid_from": payload.valid_from,
        "valid_until": payload.valid_until,
        "status": payload.status,
    }


async def build_coverage(
    session: AsyncSession,
    patient_id: uuid.UUID,
    payload: PatientCoverageCreate,
) -> PatientCoverage:
    """Create a coverage inside the caller's transaction."""

    coverage = PatientCoverage(patient_id=patient_id, **await coverage_fields(session, payload))
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
    """Catalog of payers and plans, and the coverages a patient holds under them."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_payers(self, *, search: str | None = None) -> list[Payer]:
        stmt = select(Payer).order_by(Payer.name)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(Payer.name.ilike(pattern), Payer.code.ilike(pattern)))
        return list((await self.session.scalars(stmt)).all())

    async def get_payer(self, payer_id: uuid.UUID) -> Payer:
        payer = await self.session.get(Payer, payer_id)
        if not payer:
            raise DomainError("Financiador inexistente", 404)
        return payer

    async def create_payer(self, payload: PayerCreate) -> Payer:
        async with (
            integrity_conflict(self.session, "Código de financiador duplicado"),
            self.session.begin(),
        ):
            payer = Payer(**payload.model_dump())
            self.session.add(payer)
            await self.session.flush()
            return payer

    async def update_payer(self, payer_id: uuid.UUID, payload: PayerUpdate) -> Payer:
        async with (
            integrity_conflict(self.session, "Código de financiador duplicado"),
            self.session.begin(),
        ):
            payer = await self.get_payer(payer_id)
            for field, value in payload.model_dump().items():
                setattr(payer, field, value)
            await self.session.flush()
            return payer

    async def delete_payer(self, payer_id: uuid.UUID) -> None:
        """A payer is only removable while nothing hangs from it: its plans, the coverages
        issued under it and the tariffs agreed with it all point back at this row."""

        async with (
            integrity_conflict(
                self.session,
                "No se puede eliminar un financiador con registros asociados",
            ),
            self.session.begin(),
        ):
            payer = await self.get_payer(payer_id)
            await self._require_unused(
                {
                    "planes": select(func.count())
                    .select_from(HealthPlan)
                    .where(HealthPlan.payer_id == payer_id),
                    "coberturas": select(func.count())
                    .select_from(PatientCoverage)
                    .where(PatientCoverage.payer_id == payer_id),
                    "aranceles": select(func.count())
                    .select_from(MedicalPracticeTariff)
                    .where(MedicalPracticeTariff.payer_id == payer_id),
                },
                "No se puede eliminar el financiador porque está en uso",
            )
            await self.session.delete(payer)

    async def list_health_plans(self, payer_id: uuid.UUID | None = None) -> list[HealthPlan]:
        stmt = select(HealthPlan).order_by(HealthPlan.name)
        if payer_id:
            await self.get_payer(payer_id)
            stmt = stmt.where(HealthPlan.payer_id == payer_id)
        return list((await self.session.scalars(stmt)).all())

    async def get_health_plan(self, health_plan_id: uuid.UUID) -> HealthPlan:
        plan = await self.session.get(HealthPlan, health_plan_id)
        if not plan:
            raise DomainError("Plan inexistente", 404)
        return plan

    async def create_health_plan(
        self,
        payer_id: uuid.UUID,
        payload: HealthPlanCreate,
    ) -> HealthPlan:
        async with (
            integrity_conflict(self.session, "Código de plan duplicado para el financiador"),
            self.session.begin(),
        ):
            await self.get_payer(payer_id)
            plan = HealthPlan(payer_id=payer_id, **payload.model_dump())
            self.session.add(plan)
            await self.session.flush()
            return plan

    async def update_health_plan(
        self,
        health_plan_id: uuid.UUID,
        payload: HealthPlanUpdate,
    ) -> HealthPlan:
        async with (
            integrity_conflict(self.session, "Código de plan duplicado para el financiador"),
            self.session.begin(),
        ):
            plan = await self.get_health_plan(health_plan_id)
            for field, value in payload.model_dump().items():
                setattr(plan, field, value)
            await self.session.flush()
            return plan

    async def delete_health_plan(self, health_plan_id: uuid.UUID) -> None:
        async with (
            integrity_conflict(
                self.session,
                "No se puede eliminar un plan con registros asociados",
            ),
            self.session.begin(),
        ):
            plan = await self.get_health_plan(health_plan_id)
            await self._require_unused(
                {
                    "coberturas": select(func.count())
                    .select_from(PatientCoverage)
                    .where(PatientCoverage.health_plan_id == health_plan_id),
                    "aranceles": select(func.count())
                    .select_from(MedicalPracticeTariff)
                    .where(MedicalPracticeTariff.health_plan_id == health_plan_id),
                },
                "No se puede eliminar el plan porque está en uso",
            )
            await self.session.delete(plan)

    async def list_coverages(self, patient_id: uuid.UUID) -> list[PatientCoverage]:
        await self._require_patient(patient_id)
        return list(
            (
                await self.session.scalars(
                    select(PatientCoverage)
                    .where(PatientCoverage.patient_id == patient_id)
                    .order_by(PatientCoverage.created_at.desc())
                )
            ).all()
        )

    async def get_coverage(self, coverage_id: uuid.UUID) -> PatientCoverage:
        coverage = await self.session.get(PatientCoverage, coverage_id)
        if not coverage:
            raise DomainError("Cobertura inexistente", 404)
        return coverage

    async def create_coverage(
        self,
        patient_id: uuid.UUID,
        payload: PatientCoverageCreate,
    ) -> PatientCoverage:
        async with self.session.begin():
            await self._require_patient(patient_id)
            coverage = await build_coverage(self.session, patient_id, payload)
            await self.session.flush()
            return coverage

    async def update_coverage(
        self,
        coverage_id: uuid.UUID,
        payload: PatientCoverageUpdate,
    ) -> PatientCoverage:
        """Editing a coverage re-reads the payer and the plan, so the names stored in the
        coverage keep matching the catalog.

        Admissions and accounts already opened under it are not touched: they carry their
        own snapshot of what was billed.
        """

        async with self.session.begin():
            coverage = await self.get_coverage(coverage_id)
            for field, value in (await coverage_fields(self.session, payload)).items():
                setattr(coverage, field, value)
            await self.session.flush()
            return coverage

    async def delete_coverage(self, coverage_id: uuid.UUID) -> None:
        """A coverage that was already used to admit, authorize or bill is history and stays;
        to stop using it, set its status to ``INACTIVE``."""

        async with (
            integrity_conflict(
                self.session,
                "No se puede eliminar una cobertura con registros asociados",
            ),
            self.session.begin(),
        ):
            coverage = await self.get_coverage(coverage_id)
            await self._require_unused(
                {
                    "admisiones": select(func.count())
                    .select_from(Admission)
                    .where(Admission.coverage_id == coverage_id),
                    "autorizaciones": select(func.count())
                    .select_from(Authorization)
                    .where(Authorization.patient_coverage_id == coverage_id),
                    "cuentas": select(func.count())
                    .select_from(Account)
                    .where(Account.coverage_id == coverage_id),
                },
                "No se puede eliminar la cobertura porque está en uso",
            )
            await self.session.delete(coverage)

    async def _require_unused(self, counters: dict, prefix: str) -> None:
        used = [
            label for label, stmt in counters.items() if (await self.session.scalar(stmt)) or 0
        ]
        if used:
            raise DomainError(f"{prefix}: {', '.join(used)}", 409)

    async def _require_patient(self, patient_id: uuid.UUID) -> Patient:
        patient = await self.session.get(Patient, patient_id)
        if not patient:
            raise DomainError("Paciente inexistente", 404)
        return patient
