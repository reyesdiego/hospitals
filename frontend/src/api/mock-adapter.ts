import { axiosInstance } from './custom-instance';
import {
  type MockDB,
  admissionWithEffectiveStatus,
  loadDB,
  now,
  saveDB,
  STORAGE_KEY,
  toAdmissionRead,
  uuid,
} from './mock-db';
import { handleAccountRequest } from './mock-account';
import { handleAuthRequest, roleFromAuthorization } from './mock-auth';
import { coverageFields, handleCoverageRequest, isCoverageError } from './mock-coverage';
import { handlePracticeRequest } from './mock-practices';
import {
  completeReservationForBed,
  handleWorkflowRequest,
  recordBedStatus,
  recordEvent,
} from './mock-workflow';
import type {
  AdmissionDashboardRead,
  AdmissionStatus,
  BedAssignmentRead,
  BedRead,
  BedStatus,
  FacilityRead,
  HospitalizationRead,
  HospitalizationStatus,
  PatientRead,
  RoomRead,
} from './model';

function delay(ms = 300) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** El estado de una habitacion sale de sus camas, igual que en la API. */
function roomRead(db: MockDB, room: RoomRead): RoomRead {
  const beds = db.beds.filter((bed) => bed.room_id === room.id);
  const count = (...statuses: BedStatus[]) =>
    beds.filter((bed) => statuses.includes(bed.status)).length;
  const available = count('AVAILABLE');
  const reserved = count('RESERVED');
  const occupied = count('OCCUPIED');
  const cleaning = count('PENDING_CLEANING', 'CLEANING');
  const unavailable = count('BLOCKED', 'MAINTENANCE', 'OUT_OF_SERVICE');

  const administrative = room.administrative_status ?? room.status;
  let status = administrative;
  if (administrative !== 'BLOCKED' && administrative !== 'MAINTENANCE' && beds.length > 0) {
    if (available > 0) status = 'AVAILABLE';
    else if (reserved > 0) status = 'RESERVED';
    else if (occupied > 0) status = 'OCCUPIED';
    else if (cleaning > 0) status = 'PENDING_CLEANING';
    else status = 'BLOCKED';
  }
  return {
    ...room,
    status,
    administrative_status: administrative,
    beds: beds.length,
    available_beds: available,
    reserved_beds: reserved,
    occupied_beds: occupied,
    cleaning_beds: cleaning,
    unavailable_beds: unavailable,
  };
}

function setupMockAdapter() {
  axiosInstance.defaults.adapter = async (config) => {
    await delay();
    const url = config.url ?? '';
    const method = (config.method ?? 'get').toLowerCase();
    const db = loadDB();
    const body = config.data ? JSON.parse(config.data) : {};

    // El rol sale del token, como en la API: el mock aplica las reglas que dependen de
    // quien opera (por ejemplo, el candado posterior al alta medica).
    const authorization = config.headers?.Authorization as string | undefined;
    const role = roleFromAuthorization(authorization);
    const session = handleAuthRequest(url, method, body, authorization);
    if (session) {
      if (session.kind === 'error') {
        return Promise.reject({
          response: { status: session.status, data: { detail: session.detail } },
          config,
        });
      }
      return {
        data: session.data,
        status: session.status,
        statusText: 'OK',
        headers: {},
        config,
      };
    }
    const catalog =
      handleCoverageRequest(db, url, method, body, config.params ?? {}) ??
      handlePracticeRequest(db, url, method, body, config.params ?? {}, role) ??
      handleAccountRequest(db, url, method, body, role);
    const workflow = catalog ?? handleWorkflowRequest(db, url, method, body);
    if (workflow) {
      if (workflow.kind === 'error') {
        return Promise.reject({
          response: { status: workflow.status, data: { detail: workflow.detail } },
          config,
        });
      }
      return {
        data: workflow.data,
        status: workflow.status,
        statusText: workflow.status === 201 ? 'Created' : 'OK',
        headers: {},
        config,
      };
    }

    // Patients
    if (url === '/api/v1/patients' && method === 'get') {
      return { data: db.patients, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (url === '/api/v1/patients' && method === 'post') {
      const patient: PatientRead = {
        id: uuid(),
        first_name: body.first_name,
        last_name: body.last_name,
        document_type: body.document_type,
        document_number: body.document_number,
        birth_date: body.birth_date ?? null,
        created_at: now(),
      };
      db.patients.push(patient);
      saveDB(db);
      return { data: patient, status: 201, statusText: 'Created', headers: {}, config };
    }
    const patientMatch = url.match(/^\/api\/v1\/patients\/([^/]+)$/);
    if (patientMatch && method === 'put') {
      const patient = db.patients.find((item) => item.id === patientMatch[1]);
      if (!patient) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Paciente inexistente' } }, config });
      }
      patient.first_name = body.first_name;
      patient.last_name = body.last_name;
      patient.document_type = body.document_type;
      patient.document_number = body.document_number;
      patient.birth_date = body.birth_date ?? null;
      saveDB(db);
      return { data: patient, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (patientMatch && method === 'delete') {
      const patientId = patientMatch[1];
      const hasClinicalRecords =
        db.hospitalizations.some((item) => item.patient_id === patientId) ||
        db.admissions.some((item) => item.patient_id === patientId) ||
        db.coverages.some((item) => item.patient_id === patientId);
      if (hasClinicalRecords) {
        return Promise.reject({ response: { status: 409, data: { detail: 'No se puede eliminar un paciente con registros clínicos asociados' } }, config });
      }
      db.patients = db.patients.filter((item) => item.id !== patientId);
      saveDB(db);
      return { data: undefined, status: 204, statusText: 'No Content', headers: {}, config };
    }
    if (url.startsWith('/api/v1/patients/duplicates') && method === 'get') {
      const params = config.params ?? {};
      const matches = db.patients.filter(
        (p) =>
          p.document_type === params.document_type &&
          p.document_number === params.document_number,
      );
      return { data: matches, status: 200, statusText: 'OK', headers: {}, config };
    }

    // Facilities
    if (url === '/api/v1/facilities' && method === 'get') {
      return { data: db.facilities, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (url === '/api/v1/facilities' && method === 'post') {
      const facility: FacilityRead = {
        id: uuid(),
        name: body.name,
        code: body.code,
        created_at: now(),
      };
      db.facilities.push(facility);
      saveDB(db);
      return { data: facility, status: 201, statusText: 'Created', headers: {}, config };
    }

    // Services
    if (url === '/api/v1/services' && method === 'get') {
      return { data: db.services, status: 200, statusText: 'OK', headers: {}, config };
    }

    // Rooms
    if (url === '/api/v1/rooms' && method === 'get') {
      return {
        data: db.rooms.map((room) => roomRead(db, room)),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    }
    if (url === '/api/v1/rooms' && method === 'post') {
      const room: RoomRead = {
        id: uuid(),
        facility_id: body.facility_id,
        code: body.code,
        ward: body.ward,
        status: body.status ?? 'AVAILABLE',
        administrative_status: body.status ?? 'AVAILABLE',
        created_at: now(),
      };
      db.rooms.push(room);
      saveDB(db);
      return { data: roomRead(db, room), status: 201, statusText: 'Created', headers: {}, config };
    }
    const roomMatch = url.match(/^\/api\/v1\/rooms\/([^/]+)$/);
    if (roomMatch && method === 'put') {
      const room = db.rooms.find((item) => item.id === roomMatch[1]);
      if (!room) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Habitación inexistente' } }, config });
      }
      room.facility_id = body.facility_id;
      room.code = body.code;
      room.ward = body.ward;
      // Lo que se edita es lo que se escribe sobre la habitacion; el estado sale de las camas.
      room.administrative_status = body.status;
      room.status = body.status;
      db.beds
        .filter((bed) => bed.room_id === room.id)
        .forEach((bed) => {
          bed.facility_id = room.facility_id;
          bed.ward = room.ward;
          bed.room = room.code;
        });
      saveDB(db);
      return { data: roomRead(db, room), status: 200, statusText: 'OK', headers: {}, config };
    }
    if (roomMatch && method === 'delete') {
      const roomId = roomMatch[1];
      if (db.beds.some((bed) => bed.room_id === roomId)) {
        return Promise.reject({ response: { status: 409, data: { detail: 'La habitación tiene camas asociadas' } }, config });
      }
      db.rooms = db.rooms.filter((room) => room.id !== roomId);
      saveDB(db);
      return { data: undefined, status: 204, statusText: 'No Content', headers: {}, config };
    }

    // Beds
    if (url === '/api/v1/beds' && method === 'get') {
      return { data: db.beds, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (url === '/api/v1/beds' && method === 'post') {
      const bed: BedRead = {
        id: uuid(),
        facility_id: body.facility_id,
        room_id: body.room_id,
        code: body.code,
        ward: db.rooms.find((room) => room.id === body.room_id)?.ward ?? '',
        room: db.rooms.find((room) => room.id === body.room_id)?.code ?? '',
        status: 'AVAILABLE' as BedStatus,
      };
      db.beds.push(bed);
      saveDB(db);
      return { data: bed, status: 201, statusText: 'Created', headers: {}, config };
    }
    const updateBedMatch = url.match(/^\/api\/v1\/beds\/([^/]+)$/);
    if (updateBedMatch && method === 'put') {
      const bed = db.beds.find((item) => item.id === updateBedMatch[1]);
      const room = db.rooms.find((item) => item.id === body.room_id);
      if (!bed || !room) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Cama o habitación inexistente' } }, config });
      }
      bed.facility_id = body.facility_id;
      bed.room_id = body.room_id;
      bed.code = body.code;
      bed.ward = room.ward;
      bed.room = room.code;
      saveDB(db);
      return { data: bed, status: 200, statusText: 'OK', headers: {}, config };
    }
    const bedRoomMatch = url.match(/^\/api\/v1\/beds\/([^/]+)\/room$/);
    if (bedRoomMatch && method === 'post') {
      const bed = db.beds.find((item) => item.id === bedRoomMatch[1]);
      const room = db.rooms.find((item) => item.id === body.room_id);
      if (!bed || !room) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Cama o habitación inexistente' } }, config });
      }
      bed.facility_id = room.facility_id;
      bed.room_id = room.id;
      bed.ward = room.ward;
      bed.room = room.code;
      saveDB(db);
      return { data: bed, status: 200, statusText: 'OK', headers: {}, config };
    }
    // Hospitalizations
    if (url === '/api/v1/hospitalizations' && method === 'get') {
      return { data: db.hospitalizations, status: 200, statusText: 'OK', headers: {}, config };
    }
    const hospitalizationBedAssignmentsMatch = url.match(
      /^\/api\/v1\/hospitalizations\/([^/]+)\/bed-assignments$/,
    );
    if (hospitalizationBedAssignmentsMatch && method === 'get') {
      const hospId = hospitalizationBedAssignmentsMatch[1];
      return {
        data: db.bedAssignments
          .filter((assignment) => assignment.hospitalization_id === hospId)
          .sort((a, b) => b.started_at.localeCompare(a.started_at)),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    }

    // Admissions
    if (url === '/api/v1/admissions' && method === 'get') {
      const params = config.params ?? {};
      const matches = db.admissions.filter(
        (admission) =>
          (!params.hospitalization_id ||
            admission.hospitalization_id === params.hospitalization_id) &&
          (!params.patient_id || admission.patient_id === params.patient_id),
      );
      return {
        data: matches.map((admission) => admissionWithEffectiveStatus(admission, db)),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    }
    if (url === '/api/v1/admissions' && method === 'post') {
      const patient = db.patients.find((p) => p.id === body.patient_id);
      if (!patient) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Paciente inexistente' } }, config });
      }
      if (body.coverage_id && body.coverage) {
        return Promise.reject({
          response: { status: 422, data: { detail: 'Informe coverage_id o coverage, no ambos' } },
          config,
        });
      }
      let coverage = body.coverage_id
        ? db.coverages.find(
            (item) => item.id === body.coverage_id && item.patient_id === patient.id,
          ) ?? null
        : null;
      if (body.coverage_id && !coverage) {
        return Promise.reject({
          response: { status: 404, data: { detail: 'Cobertura inexistente para el paciente' } },
          config,
        });
      }
      if (body.coverage) {
        // Same resolution as the API: the catalog fills the payer and plan names.
        const fields = coverageFields(db, body.coverage);
        if (isCoverageError(fields)) {
          return Promise.reject({
            response: { status: fields.status, data: { detail: fields.detail } },
            config,
          });
        }
        coverage = { id: uuid(), patient_id: patient.id, created_at: now(), ...fields };
        db.coverages.push(coverage);
      }
      const hospitalization: HospitalizationRead = {
        id: uuid(),
        patient_id: patient.id,
        episode_id: null,
        facility_id: body.facility_id ?? null,
        admission_type: body.admission_type ?? null,
        status: body.requested_bed_id ? 'IN_PROGRESS' : 'PENDING_BED',
        admission_reason: body.admission_reason,
        admitted_at: body.requested_bed_id ? now() : null,
        clinically_discharged_at: null,
        physically_departed_at: null,
        administratively_discharged_at: null,
        closed_at: null,
      };
      db.hospitalizations.push(hospitalization);
      db.careTeams.push({ id: uuid(), hospitalization_id: hospitalization.id, members: [] });
      if (body.requesting_service_id) {
        db.serviceAssignments.push({
          id: uuid(),
          hospitalization_id: hospitalization.id,
          service_id: body.requesting_service_id,
          started_at: now(),
          ended_at: null,
          reason: 'Servicio responsable inicial',
          assigned_by: null,
        });
      }
      recordEvent(db, 'HOSPITALIZATION_CREATED', {
        hospitalization_id: hospitalization.id,
        patient_id: patient.id,
      });
      const admission: AdmissionDashboardRead = {
        id: uuid(),
        patient_id: patient.id,
        patient,
        episode_id: uuid(),
        episode: {
          id: uuid(),
          patient_id: patient.id,
          facility_id: body.facility_id ?? null,
          episode_number: `EPI-${Date.now()}`,
          status: 'OPEN',
          reason: body.admission_reason,
          opened_at: now(),
          closed_at: null,
        },
        hospitalization_id: hospitalization.id,
        coverage_id: coverage?.id ?? body.coverage_id ?? null,
        coverage: coverage ?? null,
        facility_id: body.facility_id ?? null,
        requesting_service_id: body.requesting_service_id ?? null,
        requested_bed_id: body.requested_bed_id ?? null,
        origin: body.origin,
        admission_type: body.admission_type,
        status: body.requested_bed_id ? 'ADMITTED' : 'PENDING_BED',
        identity_validated: body.identity_validated ?? false,
        duplicate_checked: body.duplicate_checked ?? false,
        authorization_status: body.authorization_status ?? 'NOT_REQUIRED',
        authorization_number: body.authorization_number ?? null,
        responsible_contact_name: body.responsible_contact_name,
        responsible_contact_phone: body.responsible_contact_phone,
        responsible_contact_relationship: body.responsible_contact_relationship ?? null,
        admission_reason: body.admission_reason,
        responsible_physician: body.responsible_physician,
        responsible_physician_id: body.responsible_physician_id ?? null,
        presumptive_diagnosis: body.presumptive_diagnosis ?? null,
        notes: body.notes ?? null,
        requested_at: now(),
        admitted_at: body.requested_bed_id ? now() : null,
        administrative_discharged_at: null,
        created_at: now(),
        consents: (body.consents ?? []).map((consent: { consent_type: string; signed_by: string; notes?: string | null }) => ({
          id: uuid(),
          admission_id: 'pending',
          consent_type: consent.consent_type,
          signed_by: consent.signed_by,
          signed_at: now(),
          notes: consent.notes ?? null,
          created_at: now(),
        })),
      };
      admission.consents = (admission.consents ?? []).map((consent) => ({
        ...consent,
        admission_id: admission.id,
      }));
      if (body.requested_bed_id) {
        const bed = db.beds.find((b) => b.id === body.requested_bed_id);
        if (bed) {
          bed.status = 'OCCUPIED';
          bed.patient = patient;
        }
      }
      db.admissions.unshift(admission);
      if (body.authorization_status && body.authorization_status !== 'NOT_REQUIRED') {
        // ``authorizations`` is the source of truth from the first moment.
        db.authorizations.push({
          id: uuid(),
          patient_id: patient.id,
          admission_id: admission.id,
          hospitalization_id: hospitalization.id,
          patient_coverage_id: coverage?.id ?? body.coverage_id ?? null,
          authorization_type: 'ADMISSION',
          authorization_number: body.authorization_number ?? null,
          status: body.authorization_status === 'AUTHORIZED' ? 'AUTHORIZED' : 'PENDING',
          requested_at: now(),
          requested_by: null,
          resolved_at: body.authorization_status === 'AUTHORIZED' ? now() : null,
          authorized_at: body.authorization_status === 'AUTHORIZED' ? now() : null,
          valid_from: null,
          valid_until: null,
          notes: 'Registrada junto con la solicitud de admision',
          created_at: now(),
        });
      }
      recordEvent(db, 'ADMISSION_REQUESTED', {
        hospitalization_id: hospitalization.id,
        admission_id: admission.id,
        patient_id: patient.id,
      });

      saveDB(db);
      return { data: toAdmissionRead(admission), status: 201, statusText: 'Created', headers: {}, config };
    }
    const dischargeMatch = url.match(/^\/api\/v1\/admissions\/([^/]+)\/administrative-discharge$/);
    if (dischargeMatch && method === 'post') {
      const admission = db.admissions.find((a) => a.id === dischargeMatch[1]);
      if (!admission) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Admisión inexistente' } }, config });
      }
      admission.status = 'ADMINISTRATIVE_DISCHARGE';
      admission.administrative_discharged_at = now();
      saveDB(db);
      return { data: toAdmissionRead(admission), status: 200, statusText: 'OK', headers: {}, config };
    }

    // Bed assignment
    const assignMatch = url.match(
      /^\/api\/v1\/hospitalizations\/([^/]+)\/bed-assignments$/,
    );
    if (assignMatch && method === 'post') {
      const hospId = assignMatch[1];
      const bed = db.beds.find((b) => b.id === body.bed_id);
      if (!bed) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Cama inexistente' } }, config });
      }
      const reservation = completeReservationForBed(db, bed.id, hospId);
      if (reservation && reservation.status === 'ACTIVE') {
        return Promise.reject({
          response: { status: 409, data: { detail: 'La cama está reservada para otra internación' } },
          config,
        });
      }
      if (bed.status !== 'AVAILABLE' && !reservation) {
        return Promise.reject({
          response: { status: 409, data: { detail: 'La cama no está disponible' } },
          config,
        });
      }
      if (db.bedAssignments.some((item) => item.bed_id === bed.id && item.ended_at === null)) {
        return Promise.reject({
          response: { status: 409, data: { detail: 'La cama no está disponible' } },
          config,
        });
      }
      const hosp = db.hospitalizations.find((h) => h.id === hospId);
      if (!hosp) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Internación inexistente' } }, config });
      }
      if (db.bedAssignments.some((item) => item.hospitalization_id === hospId && item.ended_at === null)) {
        return Promise.reject({
          response: { status: 409, data: { detail: 'La internación ya tiene una cama activa' } },
          config,
        });
      }
      recordBedStatus(db, bed, 'OCCUPIED' as BedStatus, null, body.assignment_reason ?? null);
      hosp.status = 'IN_PROGRESS' as HospitalizationStatus;
      hosp.admitted_at = hosp.admitted_at ?? now();
      bed.patient = db.patients.find((p) => p.id === hosp.patient_id) ?? null;
      recordEvent(db, 'BED_ASSIGNED', {
        hospitalization_id: hospId,
        bed_id: bed.id,
        patient_id: hosp.patient_id,
      });
      const admission = db.admissions.find((item) => item.hospitalization_id === hospId);
      if (
        admission &&
        admission.status !== 'ADMINISTRATIVE_DISCHARGE' &&
        admission.status !== 'CANCELLED'
      ) {
        admission.status = 'ADMITTED' as AdmissionStatus;
        admission.admitted_at = admission.admitted_at ?? now();
      }
      const assignment: BedAssignmentRead = {
        id: uuid(),
        hospitalization_id: hospId,
        bed_id: body.bed_id,
        started_at: now(),
        ended_at: null,
      };
      db.bedAssignments.push(assignment);
      saveDB(db);
      return { data: assignment, status: 201, statusText: 'Created', headers: {}, config };
    }

    // Release bed
    const releaseMatch = url.match(
      /^\/api\/v1\/hospitalizations\/([^/]+)\/release-bed$/,
    );
    if (releaseMatch && method === 'post') {
      const hospId = releaseMatch[1];
      const assignment = db.bedAssignments.find(
        (a) => a.hospitalization_id === hospId && a.ended_at === null,
      );
      if (assignment) {
        const at = now();
        assignment.ended_at = at;
        const bed = db.beds.find((b) => b.id === assignment.bed_id);
        if (bed) {
          recordBedStatus(db, bed, 'PENDING_CLEANING' as BedStatus, null, 'Liberacion de cama');
          recordEvent(db, 'BED_RELEASED', { hospitalization_id: hospId, bed_id: bed.id });
        }
        const hosp = db.hospitalizations.find((h) => h.id === hospId);
        if (hosp) {
          hosp.status = 'CLINICALLY_DISCHARGED' as HospitalizationStatus;
          hosp.clinically_discharged_at = hosp.clinically_discharged_at ?? at;
          hosp.physically_departed_at = at;
          recordEvent(db, 'CLINICAL_DISCHARGE_COMPLETED', { hospitalization_id: hospId });
          recordEvent(db, 'PATIENT_PHYSICALLY_DEPARTED', {
            hospitalization_id: hospId,
            bed_id: assignment.bed_id,
            patient_id: hosp.patient_id,
          });
        }
        saveDB(db);
        return { data: assignment, status: 200, statusText: 'OK', headers: {}, config };
      }
      return Promise.reject({ response: { status: 404, data: { detail: 'No active assignment' } }, config });
    }

    // Health
    if (url === '/health' && method === 'get') {
      return { data: { status: 'healthy' }, status: 200, statusText: 'OK', headers: {}, config };
    }

    return Promise.reject({ response: { status: 404, data: { detail: 'Not found' } }, config });
  };
}

export function initMockAdapter() {
  setupMockAdapter();
}

export function resetMockDB() {
  localStorage.removeItem(STORAGE_KEY);
}
