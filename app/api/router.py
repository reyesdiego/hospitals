import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DbSession
from app.core.exceptions import DomainError
from app.models.admission import Admission, AdmissionConsent, Episode, PatientCoverage
from app.models.bed import Bed, BedAssignment
from app.models.facility import Facility
from app.models.hospitalization import Hospitalization
from app.models.patient import Patient
from app.models.room import Room
from app.models.service import Service
from app.schemas.domain import (
    AdministrativeDischargeCreate,
    AdmissionCreate,
    AdmissionConsentRead,
    AdmissionDashboardRead,
    AdmissionRead,
    BedAssignmentCreate,
    BedAssignmentRead,
    BedCreate,
    BedRead,
    BedRoomAssignmentCreate,
    BedStatusCreate,
    BedUpdate,
    FacilityCreate,
    FacilityRead,
    HospitalizationCreate,
    HospitalizationRead,
    EpisodeRead,
    PatientCoverageCreate,
    PatientCoverageRead,
    PatientCreate,
    PatientRead,
    RoomCreate,
    RoomRead,
    RoomUpdate,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)
from app.services.admission import AdmissionWorkflowService
from app.services.bed_assignment import BedAssignmentService
from app.services.room import RoomService

router = APIRouter()


async def bed_read(obj: Bed, session: DbSession, room: Room | None = None) -> BedRead:
    room = room or await session.get(Room, obj.room_id)
    if not room:
        raise DomainError("La cama no tiene una habitación válida", 500)
    status_value = await BedAssignmentService(session).current_status(obj.id)
    return BedRead(
        id=obj.id,
        facility_id=obj.facility_id,
        room_id=obj.room_id,
        code=obj.code,
        ward=obj.ward,
        room=room.code,
        status=status_value,
        patient=None,
    )


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


@router.get("/patients/{patient_id}/coverages", response_model=list[PatientCoverageRead])
async def list_patient_coverages(patient_id: uuid.UUID, session: DbSession):
    patient = await session.get(Patient, patient_id)
    if not patient:
        raise DomainError("Paciente inexistente", 404)
    return list(
        (
            await session.scalars(
                select(PatientCoverage).where(PatientCoverage.patient_id == patient_id)
            )
        ).all()
    )


@router.post("/patients/{patient_id}/coverages", response_model=PatientCoverageRead, status_code=201)
async def create_patient_coverage(
    patient_id: uuid.UUID,
    payload: PatientCoverageCreate,
    session: DbSession,
):
    patient = await session.get(Patient, patient_id)
    if not patient:
        raise DomainError("Paciente inexistente", 404)
    obj = PatientCoverage(
        **payload.model_dump(exclude={"patient_id"}),
        patient_id=patient_id,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


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
    return await bed_read(obj, session)


@router.get("/beds", response_model=list[BedRead])
async def list_beds(session: DbSession):
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(Bed, BedAssignment, Patient)
            .join(Room, Room.id == Bed.room_id)
            .outerjoin(
                BedAssignment,
                and_(
                    BedAssignment.bed_id == Bed.id,
                    BedAssignment.started_at <= now,
                    or_(BedAssignment.ended_at.is_(None), BedAssignment.ended_at > now),
                ),
            )
            .outerjoin(Hospitalization, Hospitalization.id == BedAssignment.hospitalization_id)
            .outerjoin(Patient, Patient.id == Hospitalization.patient_id)
            .order_by(Room.ward, Room.code, Bed.code)
        )
    ).all()

    return [
        BedRead(
            id=bed.id,
            facility_id=bed.facility_id,
            room_id=bed.room_id,
            code=bed.code,
            ward=bed.ward,
            room=(await session.get(Room, bed.room_id)).code,
            status=BedAssignmentService.status_from_assignment(assignment),
            patient=PatientRead.model_validate(patient) if patient else None,
        )
        for bed, assignment, patient in rows
    ]


@router.put("/beds/{bed_id}", response_model=BedRead)
async def update_bed(bed_id: uuid.UUID, payload: BedUpdate, session: DbSession):
    obj = await RoomService(session).update_bed(bed_id, payload)
    return await bed_read(obj, session)


@router.post("/beds/{bed_id}/room", response_model=BedRead)
async def assign_bed_room(
    bed_id: uuid.UUID,
    payload: BedRoomAssignmentCreate,
    session: DbSession,
):
    obj = await RoomService(session).assign_bed_room(bed_id, payload)
    return await bed_read(obj, session)


@router.post("/beds/{bed_id}/status", response_model=BedAssignmentRead | None)
async def set_bed_status(bed_id: uuid.UUID, payload: BedStatusCreate, session: DbSession):
    return await BedAssignmentService(session).set_status(
        bed_id,
        payload.status,
        payload.started_at,
        payload.ended_at,
    )


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
    obj = Hospitalization(**payload.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.get("/hospitalizations", response_model=list[HospitalizationRead])
async def list_hospitalizations(session: DbSession):
    return list((await session.scalars(select(Hospitalization))).all())


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
    return AdmissionDashboardRead(
        **AdmissionRead.model_validate(admission).model_dump(),
        patient=PatientRead.model_validate(patient),
        episode=EpisodeRead.model_validate(episode) if episode else None,
        coverage=PatientCoverageRead.model_validate(coverage) if coverage else None,
        consents=[AdmissionConsentRead.model_validate(consent) for consent in consents],
    )


@router.get("/admissions", response_model=list[AdmissionDashboardRead])
async def list_admissions(session: DbSession):
    rows = (
        await session.execute(
            select(Admission, Patient, Episode, PatientCoverage)
            .join(Patient, Patient.id == Admission.patient_id)
            .outerjoin(Episode, Episode.id == Admission.episode_id)
            .outerjoin(PatientCoverage, PatientCoverage.id == Admission.coverage_id)
            .order_by(Admission.created_at.desc())
        )
    ).all()
    return [
        await admission_dashboard_read(admission, patient, session, episode, coverage)
        for admission, patient, episode, coverage in rows
    ]


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
    return await BedAssignmentService(session).assign(hospitalization_id, payload.bed_id)


@router.post("/hospitalizations/{hospitalization_id}/release-bed", response_model=BedAssignmentRead)
async def release_bed(hospitalization_id: uuid.UUID, session: DbSession):
    return await BedAssignmentService(session).release(hospitalization_id)


api_router = router
