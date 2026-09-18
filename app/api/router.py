import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.admission_router import router as admission_router
from app.api.bed_router import router as bed_router
from app.api.dependencies import DbSession
from app.api.hospitalization_router import router as hospitalization_router
from app.api.practice_router import router as practice_router
from app.api.presenters import bed_read
from app.api.registry_router import router as registry_router
from app.core.exceptions import DomainError
from app.models.admission import (
    Admission,
    AdmissionConsent,
    AdmissionStatus,
    Episode,
)
from app.models.bed import BedTransfer
from app.models.coverage import PatientCoverage
from app.models.facility import Facility
from app.models.hospitalization import Hospitalization, HospitalizationStatus
from app.models.patient import Patient
from app.models.professional import Professional, ProfessionalSpecialty, Specialty
from app.models.room import Room
from app.models.service import Service
from app.schemas.domain import (
    AdministrativeDischargeCreate,
    AdmissionConsentRead,
    AdmissionCreate,
    AdmissionDashboardRead,
    AdmissionRead,
    BedAssignmentCreate,
    BedAssignmentRead,
    BedCreate,
    BedRead,
    BedRoomAssignmentCreate,
    BedStatusCreate,
    BedTransferCreate,
    BedTransferRead,
    BedUpdate,
    EpisodeRead,
    FacilityCreate,
    FacilityRead,
    HospitalizationCreate,
    HospitalizationRead,
    PatientCoverageRead,
    PatientCreate,
    PatientRead,
    PatientUpdate,
    ProfessionalCreate,
    ProfessionalRead,
    ProfessionalSpecialtyCreate,
    ProfessionalUpdate,
    RoomCreate,
    RoomRead,
    RoomUpdate,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
    SpecialtyCreate,
    SpecialtyRead,
    SpecialtyUpdate,
)
from app.services.admission import AdmissionWorkflowService
from app.services.bed_assignment import BedAssignmentService
from app.services.bed_status import BedStatusService
from app.services.hospitalization import HospitalizationService
from app.services.room import RoomService

router = APIRouter()


@router.post("/patients", response_model=PatientRead, status_code=201)
async def create_patient(payload: PatientCreate, session: DbSession):
    obj = Patient(**payload.model_dump())
    session.add(obj)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Documento duplicado", 409) from exc

    await session.refresh(obj)
    return obj


@router.get("/patients", response_model=list[PatientRead])
async def list_patients(session: DbSession):
    return list((await session.scalars(select(Patient))).all())


@router.put("/patients/{patient_id}", response_model=PatientRead)
async def update_patient(patient_id: uuid.UUID, payload: PatientUpdate, session: DbSession):
    obj = await session.get(Patient, patient_id)
    if not obj:
        raise DomainError("Paciente inexistente", 404)

    for field, value in payload.model_dump().items():
        setattr(obj, field, value)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Documento duplicado", 409) from exc

    await session.refresh(obj)
    return obj


@router.delete("/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(patient_id: uuid.UUID, session: DbSession):
    obj = await session.get(Patient, patient_id)
    if not obj:
        raise DomainError("Paciente inexistente", 404)

    try:
        await session.delete(obj)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("No se puede eliminar un paciente con registros clínicos asociados", 409) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/patients/duplicates", response_model=list[PatientRead])
async def find_duplicate_patients(
    document_type: str,
    document_number: str,
    session: DbSession,
):
    return list(
        (
            await session.scalars(
                select(Patient).where(
                    Patient.document_type == document_type,
                    Patient.document_number == document_number,
                )
            )
        ).all()
    )


def professional_options():
    return selectinload(Professional.specialty_links).selectinload(ProfessionalSpecialty.specialty)


async def validate_professional_specialties(
    specialties: list[ProfessionalSpecialtyCreate],
    session: DbSession,
) -> None:
    specialty_ids = [item.specialty_id for item in specialties]
    if len(set(specialty_ids)) != len(specialty_ids):
        raise DomainError("Especialidad duplicada para el profesional", 409)
    if not specialty_ids:
        return
    existing_ids = set(
        (
            await session.scalars(
                select(Specialty.id).where(Specialty.id.in_(specialty_ids))
            )
        ).all()
    )
    if existing_ids != set(specialty_ids):
        raise DomainError("Especialidad inexistente", 404)


def sync_professional_specialties(
    professional: Professional,
    specialties: list[ProfessionalSpecialtyCreate],
) -> None:
    existing_by_specialty = {link.specialty_id: link for link in professional.specialty_links}
    requested_ids = {item.specialty_id for item in specialties}

    professional.specialty_links = [
        link for link in professional.specialty_links if link.specialty_id in requested_ids
    ]

    for item in specialties:
        link = existing_by_specialty.get(item.specialty_id)
        if link:
            link.license_number = item.license_number
        else:
            professional.specialty_links.append(
                ProfessionalSpecialty(
                    specialty_id=item.specialty_id,
                    license_number=item.license_number,
                )
            )


@router.get("/specialties", response_model=list[SpecialtyRead])
async def list_specialties(session: DbSession):
    return list((await session.scalars(select(Specialty).order_by(Specialty.name))).all())


@router.post("/specialties", response_model=SpecialtyRead, status_code=201)
async def create_specialty(payload: SpecialtyCreate, session: DbSession):
    obj = Specialty(**payload.model_dump())
    session.add(obj)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Código de especialidad duplicado", 409) from exc

    await session.refresh(obj)
    return obj


@router.put("/specialties/{specialty_id}", response_model=SpecialtyRead)
async def update_specialty(specialty_id: uuid.UUID, payload: SpecialtyUpdate, session: DbSession):
    obj = await session.get(Specialty, specialty_id)
    if not obj:
        raise DomainError("Especialidad inexistente", 404)

    obj.name = payload.name
    obj.code = payload.code

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Código de especialidad duplicado", 409) from exc

    await session.refresh(obj)
    return obj


@router.delete("/specialties/{specialty_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_specialty(specialty_id: uuid.UUID, session: DbSession):
    obj = await session.get(Specialty, specialty_id)
    if not obj:
        raise DomainError("Especialidad inexistente", 404)

    try:
        await session.delete(obj)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("No se puede eliminar una especialidad asignada", 409) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/professionals", response_model=list[ProfessionalRead])
async def list_professionals(session: DbSession):
    return list(
        (
            await session.scalars(
                select(Professional)
                .options(professional_options())
                .order_by(Professional.last_name, Professional.first_name)
            )
        ).unique().all()
    )


@router.post("/professionals", response_model=ProfessionalRead, status_code=201)
async def create_professional(payload: ProfessionalCreate, session: DbSession):
    await validate_professional_specialties(payload.specialties, session)
    values = payload.model_dump(exclude={"specialties"})
    obj = Professional(**values)
    obj.specialty_links = [
        ProfessionalSpecialty(
            specialty_id=item.specialty_id,
            license_number=item.license_number,
        )
        for item in payload.specialties
    ]
    session.add(obj)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Documento o matrícula duplicada", 409) from exc

    result = await session.scalar(
        select(Professional).options(professional_options()).where(Professional.id == obj.id)
    )
    return result


@router.put("/professionals/{professional_id}", response_model=ProfessionalRead)
async def update_professional(
    professional_id: uuid.UUID,
    payload: ProfessionalUpdate,
    session: DbSession,
):
    obj = await session.scalar(
        select(Professional).options(professional_options()).where(Professional.id == professional_id)
    )
    if not obj:
        raise DomainError("Profesional inexistente", 404)

    await validate_professional_specialties(payload.specialties, session)
    for field, value in payload.model_dump(exclude={"specialties"}).items():
        setattr(obj, field, value)
    sync_professional_specialties(obj, payload.specialties)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Documento o matrícula duplicada", 409) from exc

    result = await session.scalar(
        select(Professional).options(professional_options()).where(Professional.id == professional_id)
    )
    return result


@router.delete("/professionals/{professional_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_professional(professional_id: uuid.UUID, session: DbSession):
    obj = await session.get(Professional, professional_id)
    if not obj:
        raise DomainError("Profesional inexistente", 404)

    await session.delete(obj)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/facilities", response_model=FacilityRead, status_code=201)
async def create_facility(payload: FacilityCreate, session: DbSession):
    obj = Facility(**payload.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.get("/facilities", response_model=list[FacilityRead])
async def list_facilities(session: DbSession):
    return list((await session.scalars(select(Facility))).all())


@router.get("/services", response_model=list[ServiceRead])
async def list_services(session: DbSession):
    return list((await session.scalars(select(Service))).all())


@router.post("/services", response_model=ServiceRead, status_code=201)
async def create_service(payload: ServiceCreate, session: DbSession):
    obj = Service(**payload.model_dump())
    session.add(obj)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Código de servicio duplicado", 409) from exc

    await session.refresh(obj)
    return obj


@router.put("/services/{service_id}", response_model=ServiceRead)
async def update_service(service_id: uuid.UUID, payload: ServiceUpdate, session: DbSession):
    obj = await session.get(Service, service_id)
    if not obj:
        raise DomainError("Servicio inexistente", 404)

    obj.name = payload.name
    obj.code = payload.code

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("Código de servicio duplicado", 409) from exc

    await session.refresh(obj)
    return obj


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: uuid.UUID, session: DbSession):
    obj = await session.get(Service, service_id)
    if not obj:
        raise DomainError("Servicio inexistente", 404)

    await session.delete(obj)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/beds", response_model=BedRead, status_code=201)
async def create_bed(payload: BedCreate, session: DbSession):
    obj = await RoomService(session).create_bed(payload)
    return await bed_read(session, obj)


@router.get("/beds", response_model=list[BedRead])
async def list_beds(session: DbSession):
    """Beds board: operational status, patient occupying the bed and reservation holder."""

    rows = await BedStatusService(session).board()
    return [
        BedRead(
            id=bed.id,
            facility_id=bed.facility_id,
            room_id=bed.room_id,
            code=bed.code,
            ward=bed.ward,
            room=room.code,
            status=bed.status,
            patient=PatientRead.model_validate(occupant) if occupant else None,
            reserved_for=PatientRead.model_validate(holder) if holder else None,
            reservation_expires_at=expires_at,
        )
        for bed, room, occupant, holder, expires_at in rows
    ]


@router.put("/beds/{bed_id}", response_model=BedRead)
async def update_bed(bed_id: uuid.UUID, payload: BedUpdate, session: DbSession):
    obj = await RoomService(session).update_bed(bed_id, payload)
    return await bed_read(session, obj)


@router.post("/beds/{bed_id}/room", response_model=BedRead)
async def assign_bed_room(
    bed_id: uuid.UUID,
    payload: BedRoomAssignmentCreate,
    session: DbSession,
):
    obj = await RoomService(session).assign_bed_room(bed_id, payload)
    return await bed_read(session, obj)


@router.post("/beds/{bed_id}/status", response_model=BedRead)
async def set_bed_status(bed_id: uuid.UUID, payload: BedStatusCreate, session: DbSession):
    """Operational status of a bed. Occupancy and reservation are driven by the
    hospitalization endpoints and are recorded in ``bed_status_history``."""

    bed = await BedStatusService(session).set_status(
        bed_id,
        payload.status,
        changed_by=payload.changed_by,
        reason=payload.reason,
    )
    return await bed_read(session, bed)


@router.get("/rooms", response_model=list[RoomRead])
async def list_rooms(session: DbSession):
    return list((await session.scalars(select(Room).order_by(Room.ward, Room.code))).all())


@router.post("/rooms", response_model=RoomRead, status_code=201)
async def create_room(payload: RoomCreate, session: DbSession):
    return await RoomService(session).create_room(payload)


@router.put("/rooms/{room_id}", response_model=RoomRead)
async def update_room(room_id: uuid.UUID, payload: RoomUpdate, session: DbSession):
    return await RoomService(session).update_room(room_id, payload)


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(room_id: uuid.UUID, session: DbSession):
    await RoomService(session).delete_room(room_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/hospitalizations", response_model=HospitalizationRead, status_code=201)
async def create_hospitalization(payload: HospitalizationCreate, session: DbSession):
    """Create the hospitalization of an admission request.

    An inpatient process cannot exist without the request that justifies it, so the
    patient, episode, facility and type are taken from ``admission_id``.
    """

    return await HospitalizationService(session).create_from_admission(payload)


@router.get("/hospitalizations", response_model=list[HospitalizationRead])
async def list_hospitalizations(session: DbSession):
    return list((await session.scalars(select(Hospitalization))).all())


@router.get(
    "/hospitalizations/{hospitalization_id}/bed-assignments",
    response_model=list[BedAssignmentRead],
)
async def list_hospitalization_bed_assignments(
    hospitalization_id: uuid.UUID,
    session: DbSession,
):
    await HospitalizationService(session).get(hospitalization_id)
    return await BedAssignmentService(session).list_for_hospitalization(hospitalization_id)


async def admission_dashboard_read(
    admission: Admission,
    patient: Patient,
    session: DbSession,
    episode: Episode | None = None,
    coverage: PatientCoverage | None = None,
) -> AdmissionDashboardRead:
    consents = list(
        (
            await session.scalars(
                select(AdmissionConsent).where(AdmissionConsent.admission_id == admission.id)
            )
        ).all()
    )
    admission_data = AdmissionRead.model_validate(admission).model_dump()
    if (
        admission.status == AdmissionStatus.PENDING_BED
        and admission.hospitalization_id is not None
    ):
        hospitalization = await session.get(Hospitalization, admission.hospitalization_id)
        if hospitalization and hospitalization.status == HospitalizationStatus.IN_PROGRESS:
            admission_data["status"] = AdmissionStatus.ADMITTED
            admission_data["admitted_at"] = admission.admitted_at or hospitalization.admitted_at

    return AdmissionDashboardRead(
        **admission_data,
        patient=PatientRead.model_validate(patient),
        episode=EpisodeRead.model_validate(episode) if episode else None,
        coverage=PatientCoverageRead.model_validate(coverage) if coverage else None,
        consents=[AdmissionConsentRead.model_validate(consent) for consent in consents],
    )


@router.get("/admissions", response_model=list[AdmissionDashboardRead])
async def list_admissions(
    session: DbSession,
    hospitalization_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
):
    stmt = (
        select(Admission, Patient, Episode, PatientCoverage)
        .join(Patient, Patient.id == Admission.patient_id)
        .outerjoin(Episode, Episode.id == Admission.episode_id)
        .outerjoin(PatientCoverage, PatientCoverage.id == Admission.coverage_id)
        .order_by(Admission.created_at.desc())
    )
    if hospitalization_id:
        stmt = stmt.where(Admission.hospitalization_id == hospitalization_id)
    if patient_id:
        stmt = stmt.where(Admission.patient_id == patient_id)
    rows = (await session.execute(stmt)).all()
    return [
        await admission_dashboard_read(admission, patient, session, episode, coverage)
        for admission, patient, episode, coverage in rows
    ]


@router.get("/admissions/{admission_id}", response_model=AdmissionDashboardRead)
async def get_admission(admission_id: uuid.UUID, session: DbSession):
    row = (
        await session.execute(
            select(Admission, Patient, Episode, PatientCoverage)
            .join(Patient, Patient.id == Admission.patient_id)
            .outerjoin(Episode, Episode.id == Admission.episode_id)
            .outerjoin(PatientCoverage, PatientCoverage.id == Admission.coverage_id)
            .where(Admission.id == admission_id)
        )
    ).first()
    if not row:
        raise DomainError("Admisión inexistente", 404)
    admission, patient, episode, coverage = row
    return await admission_dashboard_read(admission, patient, session, episode, coverage)


@router.post("/admissions", response_model=AdmissionRead, status_code=201)
async def create_admission(payload: AdmissionCreate, session: DbSession):
    return await AdmissionWorkflowService(session).create(payload)


@router.post("/admissions/{admission_id}/administrative-discharge", response_model=AdmissionRead)
async def administrative_discharge(
    admission_id: uuid.UUID,
    payload: AdministrativeDischargeCreate,
    session: DbSession,
):
    return await AdmissionWorkflowService(session).administrative_discharge(admission_id, payload)


@router.post(
    "/hospitalizations/{hospitalization_id}/bed-assignments",
    response_model=BedAssignmentRead,
    status_code=201,
)
async def assign_bed(
    hospitalization_id: uuid.UUID,
    payload: BedAssignmentCreate,
    session: DbSession,
):
    return await BedAssignmentService(session).assign(
        hospitalization_id,
        payload.bed_id,
        assignment_reason=payload.assignment_reason,
        assigned_by=payload.assigned_by,
    )


@router.post(
    "/hospitalizations/{hospitalization_id}/release-bed",
    response_model=BedAssignmentRead,
    deprecated=True,
)
async def release_bed(hospitalization_id: uuid.UUID, session: DbSession):
    """Compatibility endpoint. Registers the clinical discharge, if it is still missing,
    and the physical departure as separate events. Prefer ``/clinical-discharge`` followed
    by ``/physical-departure``."""

    return await HospitalizationService(session).release_bed(hospitalization_id)


@router.post(
    "/hospitalizations/{hospitalization_id}/transfers",
    response_model=BedTransferRead,
    status_code=201,
)
async def transfer_bed(
    hospitalization_id: uuid.UUID,
    payload: BedTransferCreate,
    session: DbSession,
):
    return await BedAssignmentService(session).transfer(
        hospitalization_id,
        payload.destination_bed_id,
        reason=payload.reason,
        requested_by=payload.requested_by,
        completed_by=payload.completed_by,
        service_id=payload.service_id,
    )


@router.get(
    "/hospitalizations/{hospitalization_id}/transfers",
    response_model=list[BedTransferRead],
)
async def list_bed_transfers(hospitalization_id: uuid.UUID, session: DbSession):
    hospitalization = await session.get(Hospitalization, hospitalization_id)
    if not hospitalization:
        raise DomainError("Internación inexistente", 404)
    return list(
        (
            await session.scalars(
                select(BedTransfer)
                .where(BedTransfer.hospitalization_id == hospitalization_id)
                .order_by(BedTransfer.requested_at.desc())
            )
        ).all()
    )


api_router = APIRouter()
api_router.include_router(router)
api_router.include_router(registry_router)
api_router.include_router(admission_router)
api_router.include_router(hospitalization_router)
api_router.include_router(bed_router)
api_router.include_router(practice_router)
