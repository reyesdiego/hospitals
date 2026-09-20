import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.admission import (
    AdmissionOrigin,
    AdmissionStatus,
    AdmissionType,
    AuthorizationStatus,
    ConsentType,
    EpisodeStatus,
)
from app.models.bed import BedStatus, TransferStatus
from app.models.coverage import CoverageStatus
from app.models.hospitalization import HospitalizationStatus
from app.models.room import RoomStatus


class ORMModel(BaseModel): model_config=ConfigDict(from_attributes=True)
class PatientCreate(BaseModel):
    first_name:str=Field(min_length=1,max_length=100); last_name:str=Field(min_length=1,max_length=100); document_type:str; document_number:str; birth_date:date|None=None
class PatientUpdate(PatientCreate): pass
class PatientRead(ORMModel):
    id:uuid.UUID; first_name:str; last_name:str; document_type:str; document_number:str; birth_date:date|None; created_at:datetime
class SpecialtyCreate(BaseModel): name:str=Field(min_length=1,max_length=150); code:str=Field(min_length=1,max_length=30)
class SpecialtyUpdate(BaseModel): name:str=Field(min_length=1,max_length=150); code:str=Field(min_length=1,max_length=30)
class SpecialtyRead(ORMModel): id:uuid.UUID; name:str; code:str; created_at:datetime
class ProfessionalSpecialtyCreate(BaseModel):
    specialty_id:uuid.UUID
    license_number:str=Field(min_length=1,max_length=80)
class ProfessionalSpecialtyRead(ORMModel):
    id:uuid.UUID
    specialty_id:uuid.UUID
    specialty:SpecialtyRead
    license_number:str
    created_at:datetime
class ProfessionalCreate(BaseModel):
    first_name:str=Field(min_length=1,max_length=100)
    last_name:str=Field(min_length=1,max_length=100)
    document_type:str=Field(min_length=1,max_length=30)
    document_number:str=Field(min_length=1,max_length=50)
    email:str|None=Field(default=None,max_length=150)
    phone:str|None=Field(default=None,max_length=80)
    specialties:list[ProfessionalSpecialtyCreate]=Field(default_factory=list)
class ProfessionalUpdate(ProfessionalCreate): pass
class ProfessionalRead(ORMModel):
    id:uuid.UUID
    first_name:str
    last_name:str
    document_type:str
    document_number:str
    email:str|None
    phone:str|None
    specialties:list[ProfessionalSpecialtyRead]=Field(default_factory=list)
    created_at:datetime
class FacilityCreate(BaseModel): name:str; code:str
class FacilityRead(ORMModel): id:uuid.UUID; name:str; code:str; created_at:datetime
class ServiceCreate(BaseModel): name:str; code:str
class ServiceUpdate(BaseModel): name:str; code:str
class ServiceRead(ORMModel): id:uuid.UUID; name:str; code:str; created_at:datetime
class RoomCreate(BaseModel):
    facility_id: uuid.UUID
    code: str = Field(min_length=1, max_length=50)
    ward: str = Field(min_length=1, max_length=100)
    status: RoomStatus = RoomStatus.AVAILABLE


class RoomUpdate(BaseModel):
    facility_id: uuid.UUID
    code: str = Field(min_length=1, max_length=50)
    ward: str = Field(min_length=1, max_length=100)
    status: RoomStatus


class RoomRead(ORMModel):
    """``status`` es el estado real: sale de las camas de la habitación.

    ``administrative_status`` es lo que se dejó escrito sobre la habitación misma, que solo
    manda cuando está bloqueada o en mantenimiento.
    """

    id: uuid.UUID
    facility_id: uuid.UUID
    code: str
    ward: str
    status: RoomStatus
    administrative_status: RoomStatus
    beds: int = 0
    available_beds: int = 0
    reserved_beds: int = 0
    occupied_beds: int = 0
    cleaning_beds: int = 0
    unavailable_beds: int = 0
    created_at: datetime


class BedCreate(BaseModel):
    facility_id: uuid.UUID
    room_id: uuid.UUID
    code: str = Field(min_length=1, max_length=50)


class BedUpdate(BaseModel):
    facility_id: uuid.UUID
    room_id: uuid.UUID
    code: str = Field(min_length=1, max_length=50)


class BedRoomAssignmentCreate(BaseModel):
    room_id: uuid.UUID


class BedRead(BaseModel):
    id:uuid.UUID
    facility_id:uuid.UUID
    room_id:uuid.UUID
    code:str
    ward:str
    room:str
    status:BedStatus
    patient:PatientRead|None=None
    reserved_for:PatientRead|None=None
    reservation_expires_at:datetime|None=None
class HospitalizationCreate(BaseModel):
    """A hospitalization always originates in an admission request."""

    admission_id: uuid.UUID
    facility_id: uuid.UUID | None = None
    responsible_service_id: uuid.UUID | None = None
    attending_physician_id: uuid.UUID | None = None


class HospitalizationRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    episode_id: uuid.UUID | None
    facility_id: uuid.UUID | None
    admission_type: AdmissionType | None
    status: HospitalizationStatus
    admission_reason: str
    admitted_at: datetime | None
    clinically_discharged_at: datetime | None
    physically_departed_at: datetime | None
    administratively_discharged_at: datetime | None
    closed_at: datetime | None
class BedAssignmentCreate(BaseModel):
    bed_id:uuid.UUID
    assignment_reason:str|None=Field(default=None,max_length=500)
    assigned_by:str|None=Field(default=None,max_length=150)
class BedStatusCreate(BaseModel):
    status: BedStatus
    changed_by: str | None = Field(default=None, max_length=150)
    reason: str | None = Field(default=None, max_length=500)
class BedAssignmentRead(ORMModel):
    id:uuid.UUID
    hospitalization_id:uuid.UUID
    bed_id:uuid.UUID
    started_at:datetime
    ended_at:datetime|None
    assignment_reason:str|None=None
    assigned_by:str|None=None
    ended_by:str|None=None
class BedTransferCreate(BaseModel):
    destination_bed_id:uuid.UUID
    service_id:uuid.UUID|None=None
    reason:str|None=Field(default=None,max_length=500)
    requested_by:str|None=Field(default=None,max_length=150)
    completed_by:str|None=Field(default=None,max_length=150)
class BedTransferRead(ORMModel):
    id:uuid.UUID
    hospitalization_id:uuid.UUID
    from_bed_id:uuid.UUID
    to_bed_id:uuid.UUID
    status:TransferStatus
    requested_at:datetime
    completed_at:datetime|None
    cancelled_at:datetime|None
    reason:str|None


class PatientCoverageCreate(BaseModel):
    patient_id: uuid.UUID | None = None
    payer_id: uuid.UUID | None = None
    health_plan_id: uuid.UUID | None = None
    payer_name: str | None = Field(default=None, max_length=150)
    plan_name: str | None = Field(default=None, max_length=150)
    member_number: str | None = Field(default=None, max_length=80)
    authorization_required: bool = False
    valid_from: date | None = None
    valid_until: date | None = None
    status: CoverageStatus = CoverageStatus.ACTIVE


class PatientCoverageUpdate(BaseModel):
    """The patient of a coverage is not editable; everything else is."""

    payer_id: uuid.UUID | None = None
    health_plan_id: uuid.UUID | None = None
    payer_name: str | None = Field(default=None, max_length=150)
    plan_name: str | None = Field(default=None, max_length=150)
    member_number: str | None = Field(default=None, max_length=80)
    authorization_required: bool = False
    valid_from: date | None = None
    valid_until: date | None = None
    status: CoverageStatus = CoverageStatus.ACTIVE


class PatientCoverageRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    payer_id: uuid.UUID | None
    health_plan_id: uuid.UUID | None
    payer_name: str
    plan_name: str | None
    member_number: str | None
    authorization_required: bool
    valid_from: date | None
    valid_until: date | None
    status: CoverageStatus
    created_at: datetime


class EpisodeRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    facility_id: uuid.UUID | None
    episode_number: str
    status: EpisodeStatus
    reason: str
    opened_at: datetime
    closed_at: datetime | None


class AdmissionConsentCreate(BaseModel):
    consent_type: ConsentType
    signed_by: str = Field(min_length=1, max_length=150)
    signed_at: datetime | None = None
    notes: str | None = None


class AdmissionConsentRead(ORMModel):
    id: uuid.UUID
    admission_id: uuid.UUID
    consent_type: ConsentType
    signed_by: str
    signed_at: datetime | None
    notes: str | None
    created_at: datetime


class AdmissionCreate(BaseModel):
    patient_id: uuid.UUID
    origin: AdmissionOrigin
    admission_type: AdmissionType
    facility_id: uuid.UUID | None = None
    identity_validated: bool = False
    duplicate_checked: bool = False
    coverage_id: uuid.UUID | None = None
    coverage: PatientCoverageCreate | None = None
    authorization_status: AuthorizationStatus = AuthorizationStatus.NOT_REQUIRED
    authorization_number: str | None = Field(default=None, max_length=100)
    responsible_contact_name: str = Field(min_length=1, max_length=150)
    responsible_contact_phone: str = Field(min_length=1, max_length=80)
    responsible_contact_relationship: str | None = Field(default=None, max_length=80)
    admission_reason: str = Field(min_length=3, max_length=500)
    responsible_physician: str = Field(min_length=1, max_length=150)
    responsible_physician_id: uuid.UUID | None = None
    requesting_service_id: uuid.UUID | None = None
    presumptive_diagnosis: str | None = Field(default=None, max_length=500)
    requested_bed_id: uuid.UUID | None = None
    consents: list[AdmissionConsentCreate] = Field(default_factory=list)
    notes: str | None = None
    confirm_admission: bool = True


class AdmissionRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    episode_id: uuid.UUID | None
    hospitalization_id: uuid.UUID | None
    coverage_id: uuid.UUID | None
    facility_id: uuid.UUID | None
    requesting_service_id: uuid.UUID | None
    requested_bed_id: uuid.UUID | None
    origin: AdmissionOrigin
    admission_type: AdmissionType
    status: AdmissionStatus
    identity_validated: bool
    duplicate_checked: bool
    authorization_status: AuthorizationStatus
    authorization_number: str | None
    responsible_contact_name: str
    responsible_contact_phone: str
    responsible_contact_relationship: str | None
    admission_reason: str
    responsible_physician: str
    responsible_physician_id: uuid.UUID | None
    presumptive_diagnosis: str | None
    notes: str | None
    requested_at: datetime | None
    admitted_at: datetime | None
    administrative_discharged_at: datetime | None
    created_at: datetime


class AdmissionDashboardRead(AdmissionRead):
    patient: PatientRead
    episode: EpisodeRead | None = None
    coverage: PatientCoverageRead | None = None
    consents: list[AdmissionConsentRead] = Field(default_factory=list)


class AdministrativeDischargeCreate(BaseModel):
    notes: str | None = None
    actor: str | None = Field(default=None, max_length=150)


class DuplicatePatientRead(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    document_type: str
    document_number: str
