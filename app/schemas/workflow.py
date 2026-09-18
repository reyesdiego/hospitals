"""Schemas for the hospitalization workflow: registry, authorization, beds and discharge."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.account import AccountStatus, ChargeCategory, ChargeItemStatus
from app.models.audit import HospitalizationEventType
from app.models.authorization import AuthorizationState, AuthorizationType
from app.models.bed import BedReservationStatus, BedStatus
from app.models.care_team import CareTeamRole
from app.models.discharge import DischargeDestination, DischargePlanStatus, DischargeType
from app.models.patient import PatientIdentifierType
from app.schemas.domain import ORMModel, PatientRead


class PatientIdentifierCreate(BaseModel):
    identifier_type: PatientIdentifierType
    value: str = Field(min_length=1, max_length=80)
    issuer: str | None = Field(default=None, max_length=120)
    is_primary: bool = False


class PatientIdentifierRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    identifier_type: PatientIdentifierType
    value: str
    issuer: str | None
    is_primary: bool
    created_at: datetime


class PatientContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    relationship_to_patient: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=150)
    is_primary: bool = False


class PatientContactRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    full_name: str
    relationship_to_patient: str | None
    phone: str | None
    email: str | None
    is_primary: bool
    created_at: datetime


class PatientMatchRead(BaseModel):
    """Candidate patient found while searching identifiers before creating a new one."""

    patient: PatientRead
    matched_on: str


class PayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=1, max_length=30)
    tax_id: str | None = Field(default=None, max_length=40)


class PayerRead(ORMModel):
    id: uuid.UUID
    name: str
    code: str
    tax_id: str | None
    created_at: datetime


class HealthPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=1, max_length=40)


class HealthPlanRead(ORMModel):
    id: uuid.UUID
    payer_id: uuid.UUID
    name: str
    code: str
    created_at: datetime


class AuthorizationRequestCreate(BaseModel):
    authorization_type: AuthorizationType = AuthorizationType.ADMISSION
    patient_coverage_id: uuid.UUID | None = None
    authorization_number: str | None = Field(default=None, max_length=100)
    requested_by: str | None = Field(default=None, max_length=150)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None


class AuthorizationResolveCreate(BaseModel):
    status: AuthorizationState
    authorization_number: str | None = Field(default=None, max_length=100)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None


class AuthorizationRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    admission_id: uuid.UUID | None
    hospitalization_id: uuid.UUID | None
    patient_coverage_id: uuid.UUID | None
    authorization_type: AuthorizationType
    authorization_number: str | None
    status: AuthorizationState
    requested_at: datetime
    requested_by: str | None
    resolved_at: datetime | None
    authorized_at: datetime | None
    valid_from: datetime | None
    valid_until: datetime | None
    notes: str | None
    created_at: datetime


class ServiceAssignmentCreate(BaseModel):
    service_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)
    assigned_by: str | None = Field(default=None, max_length=150)


class ServiceAssignmentRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    service_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    reason: str | None
    assigned_by: str | None


class CareTeamMemberCreate(BaseModel):
    practitioner_id: uuid.UUID
    role: CareTeamRole
    notes: str | None = Field(default=None, max_length=500)


class CareTeamMemberRead(ORMModel):
    id: uuid.UUID
    care_team_id: uuid.UUID
    practitioner_id: uuid.UUID
    role: CareTeamRole
    started_at: datetime
    ended_at: datetime | None
    notes: str | None


class CareTeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hospitalization_id: uuid.UUID
    members: list[CareTeamMemberRead] = Field(default_factory=list)


class BedReservationCreate(BaseModel):
    bed_id: uuid.UUID
    expires_in_minutes: int | None = Field(default=120, ge=1, le=10080)
    reserved_by: str | None = Field(default=None, max_length=150)
    reason: str | None = Field(default=None, max_length=500)


class BedReservationRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    bed_id: uuid.UUID
    status: BedReservationStatus
    reserved_at: datetime
    expires_at: datetime | None
    reserved_by: str | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    reason: str | None


class BedReservationCancelCreate(BaseModel):
    cancelled_by: str | None = Field(default=None, max_length=150)
    reason: str | None = Field(default=None, max_length=500)


class BedStatusHistoryRead(ORMModel):
    id: uuid.UUID
    bed_id: uuid.UUID
    previous_status: BedStatus | None
    new_status: BedStatus
    changed_at: datetime
    changed_by: str | None
    reason: str | None


class BedOperationCreate(BaseModel):
    changed_by: str | None = Field(default=None, max_length=150)
    reason: str | None = Field(default=None, max_length=500)


class BedAssignmentConfirmCreate(BaseModel):
    """Confirm the physical admission of a patient on a bed."""

    bed_id: uuid.UUID
    assignment_reason: str | None = Field(default=None, max_length=500)
    assigned_by: str | None = Field(default=None, max_length=150)


class DischargePlanCreate(BaseModel):
    planned_date: date | None = None
    destination: DischargeDestination = DischargeDestination.HOME
    requires_transport: bool = False
    requires_home_care: bool = False
    status: DischargePlanStatus = DischargePlanStatus.PLANNED
    created_by: str | None = Field(default=None, max_length=150)
    notes: str | None = None


class DischargePlanRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    planned_date: date | None
    destination: DischargeDestination
    requires_transport: bool
    requires_home_care: bool
    status: DischargePlanStatus
    created_by: str | None
    notes: str | None
    created_at: datetime


class ClinicalDischargeCreate(BaseModel):
    discharge_type: DischargeType = DischargeType.MEDICAL
    discharge_reason: str | None = Field(default=None, max_length=500)
    destination: DischargeDestination | None = None
    ordered_by: str | None = Field(default=None, max_length=150)
    ordered_by_practitioner_id: uuid.UUID | None = None
    effective_at: datetime | None = None
    instructions: str | None = None


class DischargeRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    discharge_type: DischargeType
    discharge_reason: str | None
    destination: DischargeDestination | None
    ordered_by: str | None
    ordered_by_practitioner_id: uuid.UUID | None
    ordered_at: datetime
    effective_at: datetime
    instructions: str | None


class PhysicalDepartureCreate(BaseModel):
    departed_at: datetime | None = None
    released_by: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=500)


class ChargeItemCreate(BaseModel):
    practice_id: uuid.UUID | None = None
    category: ChargeCategory
    description: str = Field(min_length=1, max_length=250)
    quantity: Decimal = Field(default=Decimal(1), gt=0)
    unit_price: Decimal = Field(ge=0)
    charged_at: datetime | None = None
    recorded_by: str | None = Field(default=None, max_length=150)
    notes: str | None = None


class ChargeItemVoidCreate(BaseModel):
    """A wrong charge is voided, never deleted: the line stays in the account."""

    reason: str | None = Field(default=None, max_length=500)
    actor: str | None = Field(default=None, max_length=150)


class ChargeItemRead(ORMModel):
    id: uuid.UUID
    account_id: uuid.UUID
    practice_id: uuid.UUID | None = None
    practice_code: str | None = None
    category: ChargeCategory
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    charged_at: datetime
    recorded_by: str | None
    notes: str | None
    status: ChargeItemStatus = ChargeItemStatus.ACTIVE
    voided_at: datetime | None = None
    voided_by: str | None = None
    void_reason: str | None = None


class AccountRead(ORMModel):
    id: uuid.UUID
    hospitalization_id: uuid.UUID
    patient_id: uuid.UUID
    coverage_id: uuid.UUID | None
    status: AccountStatus
    currency: str
    opened_at: datetime
    ready_for_review_at: datetime | None
    closed_at: datetime | None
    # ``total_amount`` only adds the active charges; the voided ones stay in the list.
    total_amount: Decimal = Decimal(0)
    voided_amount: Decimal = Decimal(0)
    charge_items: list[ChargeItemRead] = Field(default_factory=list)


class AccountCloseCreate(BaseModel):
    actor: str | None = Field(default=None, max_length=150)


class HospitalizationEventRead(ORMModel):
    id: uuid.UUID
    event_type: HospitalizationEventType
    hospitalization_id: uuid.UUID | None
    admission_id: uuid.UUID | None
    bed_id: uuid.UUID | None
    patient_id: uuid.UUID | None
    occurred_at: datetime
    actor: str | None
    details: dict | None
