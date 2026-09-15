import { axiosInstance } from './custom-instance';
import type {
  AdmissionDashboardRead,
  AdmissionRead,
  AdmissionStatus,
  AuthorizationStatus,
  BedAssignmentRead,
  BedRead,
  BedStatus,
  FacilityRead,
  HospitalizationRead,
  HospitalizationStatus,
  PatientCoverageRead,
  PatientRead,
  RoomRead,
  RoomStatus,
  ServiceRead,
} from './model';

const STORAGE_KEY = 'hosp_mock_db_v1';

type MockDB = {
  patients: PatientRead[];
  facilities: FacilityRead[];
  beds: BedRead[];
  rooms: RoomRead[];
  services: ServiceRead[];
  hospitalizations: HospitalizationRead[];
  bedAssignments: BedAssignmentRead[];
  coverages: PatientCoverageRead[];
  admissions: AdmissionDashboardRead[];
};

function uuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function now(): string {
  return new Date().toISOString();
}

function toAdmissionRead(admission: AdmissionDashboardRead): AdmissionRead {
  const read: Partial<AdmissionDashboardRead> = { ...admission };
  delete read.patient;
  delete read.episode;
  delete read.coverage;
  delete read.consents;
  return read as AdmissionRead;
}

function admissionWithEffectiveStatus(
  admission: AdmissionDashboardRead,
  db: MockDB,
): AdmissionDashboardRead {
  if (admission.status !== 'PENDING_BED' || !admission.hospitalization_id) return admission;
  const hospitalization = db.hospitalizations.find((item) => item.id === admission.hospitalization_id);
  if (hospitalization?.status !== 'IN_PROGRESS') return admission;
  return {
    ...admission,
    status: 'ADMITTED' as AdmissionStatus,
    admitted_at: admission.admitted_at ?? hospitalization.admitted_at,
  };
}

function seed(): MockDB {
  const facilities: FacilityRead[] = [
    {
      id: 'fac-001',
      name: 'Hospital General Central',
      code: 'HGC',
      created_at: '2025-01-15T10:00:00Z',
    },
    {
      id: 'fac-002',
      name: 'Clinica Santa Maria',
      code: 'CSM',
      created_at: '2025-02-20T10:00:00Z',
    },
  ];

  const rooms: RoomRead[] = [
    {
      id: 'room-101',
      facility_id: 'fac-001',
      code: '101',
      ward: 'Cardiologia',
      status: 'AVAILABLE' as RoomStatus,
      created_at: '2025-01-15T10:00:00Z',
    },
    {
      id: 'room-102',
      facility_id: 'fac-001',
      code: '102',
      ward: 'Cardiologia',
      status: 'OCCUPIED' as RoomStatus,
      created_at: '2025-01-15T10:00:00Z',
    },
    {
      id: 'room-201',
      facility_id: 'fac-001',
      code: '201',
      ward: 'Pediatria',
      status: 'AVAILABLE' as RoomStatus,
      created_at: '2025-01-15T10:00:00Z',
    },
    {
      id: 'room-301',
      facility_id: 'fac-002',
      code: '301',
      ward: 'Urgencias',
      status: 'PENDING_CLEANING' as RoomStatus,
      created_at: '2025-02-20T10:00:00Z',
    },
    {
      id: 'room-302',
      facility_id: 'fac-002',
      code: '302',
      ward: 'Urgencias',
      status: 'MAINTENANCE' as RoomStatus,
      created_at: '2025-02-20T10:00:00Z',
    },
  ];

  const beds: BedRead[] = [
    {
      id: 'bed-001',
      facility_id: 'fac-001',
      room_id: 'room-101',
      code: 'A-101',
      ward: 'Cardiologia',
      room: '101',
      status: 'AVAILABLE' as BedStatus,
    },
    {
      id: 'bed-002',
      facility_id: 'fac-001',
      room_id: 'room-102',
      code: 'A-102',
      ward: 'Cardiologia',
      room: '102',
      status: 'OCCUPIED' as BedStatus,
    },
    {
      id: 'bed-003',
      facility_id: 'fac-001',
      room_id: 'room-201',
      code: 'B-201',
      ward: 'Pediatria',
      room: '201',
      status: 'AVAILABLE' as BedStatus,
    },
    {
      id: 'bed-004',
      facility_id: 'fac-002',
      room_id: 'room-301',
      code: 'C-301',
      ward: 'Urgencias',
      room: '301',
      status: 'PENDING_CLEANING' as BedStatus,
    },
    {
      id: 'bed-005',
      facility_id: 'fac-002',
      room_id: 'room-302',
      code: 'C-302',
      ward: 'Urgencias',
      room: '302',
      status: 'MAINTENANCE' as BedStatus,
    },
  ];

  const patients: PatientRead[] = [
    {
      id: 'pat-001',
      first_name: 'Juan',
      last_name: 'Perez',
      document_type: 'DNI',
      document_number: '12345678',
      birth_date: '1985-03-15',
      created_at: '2025-06-01T08:00:00Z',
    },
    {
      id: 'pat-002',
      first_name: 'Maria',
      last_name: 'Garcia',
      document_type: 'DNI',
      document_number: '87654321',
      birth_date: '1990-07-22',
      created_at: '2025-06-15T08:00:00Z',
    },
    {
      id: 'pat-003',
      first_name: 'Carlos',
      last_name: 'Rodriguez',
      document_type: 'PASSPORT',
      document_number: 'AB123456',
      birth_date: null,
      created_at: '2025-07-01T08:00:00Z',
    },
  ];

  beds[1].patient = patients[0];

  const services: ServiceRead[] = [
    { id: 'srv-001', name: 'Cardiologia', code: 'CAR', created_at: '2025-01-01T08:00:00Z' },
    { id: 'srv-002', name: 'Cirugia', code: 'CIR', created_at: '2025-01-01T08:00:00Z' },
    { id: 'srv-003', name: 'Urgencias', code: 'URG', created_at: '2025-01-01T08:00:00Z' },
  ];

  const coverages: PatientCoverageRead[] = [
    {
      id: 'cov-001',
      patient_id: 'pat-001',
      payer_name: 'OSDE',
      plan_name: '210',
      member_number: '998877',
      authorization_required: true,
      created_at: '2025-07-20T13:30:00Z',
    },
  ];

  const hospitalizations: HospitalizationRead[] = [
    {
      id: 'hosp-001',
      patient_id: 'pat-001',
      status: 'IN_PROGRESS' as HospitalizationStatus,
      admission_reason: 'Dolor toracico agudo - evaluacion cardiaca',
      admitted_at: '2025-07-20T14:30:00Z',
      discharged_at: null,
    },
    {
      id: 'hosp-002',
      patient_id: 'pat-002',
      status: 'PENDING_BED' as HospitalizationStatus,
      admission_reason: 'Post-operatorio - observacion',
      admitted_at: null,
      discharged_at: null,
    },
  ];

  const bedAssignments: BedAssignmentRead[] = [
    {
      id: 'asg-001',
      hospitalization_id: 'hosp-001',
      bed_id: 'bed-002',
      status: 'OCCUPIED' as BedStatus,
      started_at: '2025-07-20T15:00:00Z',
      ended_at: null,
    },
  ];

  const admissions: AdmissionDashboardRead[] = [
    {
      id: 'adm-001',
      patient_id: 'pat-001',
      patient: patients[0],
      episode_id: 'epi-001',
      episode: {
        id: 'epi-001',
        patient_id: 'pat-001',
        episode_number: 'EPI-20250720143000-DEMO',
        status: 'OPEN',
        reason: 'Dolor toracico agudo - evaluacion cardiaca',
        opened_at: '2025-07-20T14:30:00Z',
        closed_at: null,
      },
      hospitalization_id: 'hosp-001',
      coverage_id: 'cov-001',
      coverage: coverages[0],
      requesting_service_id: 'srv-001',
      requested_bed_id: 'bed-002',
      origin: 'EMERGENCY_ROOM',
      admission_type: 'EMERGENCY',
      status: 'ADMITTED' as AdmissionStatus,
      identity_validated: true,
      duplicate_checked: true,
      authorization_status: 'AUTHORIZED' as AuthorizationStatus,
      authorization_number: 'AUT-4455',
      responsible_contact_name: 'Ana Perez',
      responsible_contact_phone: '+54 11 5555-1010',
      responsible_contact_relationship: 'Conyuge',
      admission_reason: 'Dolor toracico agudo - evaluacion cardiaca',
      responsible_physician: 'Dra. Alvarez',
      presumptive_diagnosis: 'Sindrome coronario a descartar',
      notes: null,
      admitted_at: '2025-07-20T15:00:00Z',
      administrative_discharged_at: null,
      consents: [
        {
          id: 'con-001',
          admission_id: 'adm-001',
          consent_type: 'GENERAL_ADMISSION',
          signed_by: 'Ana Perez',
          signed_at: '2025-07-20T14:40:00Z',
          notes: null,
          created_at: '2025-07-20T14:40:00Z',
        },
      ],
      created_at: '2025-07-20T14:30:00Z',
    },
  ];

  return { patients, facilities, beds, rooms, services, hospitalizations, bedAssignments, coverages, admissions };
}

function loadDB(): MockDB {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Partial<MockDB>;
      const seeded = seed();
      return {
        patients: parsed.patients ?? seeded.patients,
        facilities: parsed.facilities ?? seeded.facilities,
        beds: parsed.beds ?? seeded.beds,
        rooms: parsed.rooms ?? seeded.rooms,
        services: parsed.services ?? seeded.services,
        hospitalizations: parsed.hospitalizations ?? seeded.hospitalizations,
        bedAssignments: parsed.bedAssignments ?? seeded.bedAssignments,
        coverages: parsed.coverages ?? seeded.coverages,
        admissions: parsed.admissions ?? seeded.admissions,
      };
    } catch {
      // fall through to seed
    }
  }
  const db = seed();
  saveDB(db);
  return db;
}

function saveDB(db: MockDB) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(db));
}

function delay(ms = 300) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setupMockAdapter() {
  axiosInstance.defaults.adapter = async (config) => {
    await delay();
    const url = config.url ?? '';
    const method = (config.method ?? 'get').toLowerCase();
    const db = loadDB();

    // Patients
    if (url === '/api/v1/patients' && method === 'get') {
      return { data: db.patients, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (url === '/api/v1/patients' && method === 'post') {
      const body = JSON.parse(config.data);
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
      const body = JSON.parse(config.data);
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

    const coveragesMatch = url.match(/^\/api\/v1\/patients\/([^/]+)\/coverages$/);
    if (coveragesMatch && method === 'get') {
      const patientId = coveragesMatch[1];
      return {
        data: db.coverages.filter((c) => c.patient_id === patientId),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    }
    if (coveragesMatch && method === 'post') {
      const patientId = coveragesMatch[1];
      const body = JSON.parse(config.data);
      const coverage: PatientCoverageRead = {
        id: uuid(),
        patient_id: patientId,
        payer_name: body.payer_name,
        plan_name: body.plan_name ?? null,
        member_number: body.member_number ?? null,
        authorization_required: body.authorization_required ?? false,
        created_at: now(),
      };
      db.coverages.push(coverage);
      saveDB(db);
      return { data: coverage, status: 201, statusText: 'Created', headers: {}, config };
    }

    // Facilities
    if (url === '/api/v1/facilities' && method === 'get') {
      return { data: db.facilities, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (url === '/api/v1/facilities' && method === 'post') {
      const body = JSON.parse(config.data);
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
      return { data: db.rooms, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (url === '/api/v1/rooms' && method === 'post') {
      const body = JSON.parse(config.data);
      const room: RoomRead = {
        id: uuid(),
        facility_id: body.facility_id,
        code: body.code,
        ward: body.ward,
        status: body.status ?? 'AVAILABLE',
        created_at: now(),
      };
      db.rooms.push(room);
      saveDB(db);
      return { data: room, status: 201, statusText: 'Created', headers: {}, config };
    }
    const roomMatch = url.match(/^\/api\/v1\/rooms\/([^/]+)$/);
    if (roomMatch && method === 'put') {
      const room = db.rooms.find((item) => item.id === roomMatch[1]);
      if (!room) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Habitación inexistente' } }, config });
      }
      const body = JSON.parse(config.data);
      room.facility_id = body.facility_id;
      room.code = body.code;
      room.ward = body.ward;
      room.status = body.status;
      db.beds
        .filter((bed) => bed.room_id === room.id)
        .forEach((bed) => {
          bed.facility_id = room.facility_id;
          bed.ward = room.ward;
          bed.room = room.code;
        });
      saveDB(db);
      return { data: room, status: 200, statusText: 'OK', headers: {}, config };
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
      const body = JSON.parse(config.data);
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
      const body = JSON.parse(config.data);
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
      const body = JSON.parse(config.data);
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
    const bedStatusMatch = url.match(/^\/api\/v1\/beds\/([^/]+)\/status$/);
    if (bedStatusMatch && method === 'post') {
      const bed = db.beds.find((item) => item.id === bedStatusMatch[1]);
      if (!bed) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Cama inexistente' } }, config });
      }
      const body = JSON.parse(config.data);
      if (body.status === 'OCCUPIED') {
        return Promise.reject({ response: { status: 409, data: { detail: 'La ocupación se crea desde una internación' } }, config });
      }
      bed.status = body.status;
      if (body.status === 'AVAILABLE') {
        bed.patient = null;
      }
      saveDB(db);
      return { data: null, status: 200, statusText: 'OK', headers: {}, config };
    }

    // Hospitalizations
    if (url === '/api/v1/hospitalizations' && method === 'get') {
      return { data: db.hospitalizations, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (url === '/api/v1/hospitalizations' && method === 'post') {
      const body = JSON.parse(config.data);
      const hosp: HospitalizationRead = {
        id: uuid(),
        patient_id: body.patient_id,
        status: 'PENDING_BED' as HospitalizationStatus,
        admission_reason: body.admission_reason,
        admitted_at: null,
        discharged_at: null,
      };
      db.hospitalizations.push(hosp);
      saveDB(db);
      return { data: hosp, status: 201, statusText: 'Created', headers: {}, config };
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
      return {
        data: db.admissions.map((admission) => admissionWithEffectiveStatus(admission, db)),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    }
    if (url === '/api/v1/admissions' && method === 'post') {
      const body = JSON.parse(config.data);
      const patient = db.patients.find((p) => p.id === body.patient_id);
      if (!patient) {
        return Promise.reject({ response: { status: 404, data: { detail: 'Paciente inexistente' } }, config });
      }
      const coverage = body.coverage
        ? {
            id: uuid(),
            patient_id: patient.id,
            payer_name: body.coverage.payer_name,
            plan_name: body.coverage.plan_name ?? null,
            member_number: body.coverage.member_number ?? null,
            authorization_required: body.coverage.authorization_required ?? false,
            created_at: now(),
          }
        : null;
      if (coverage) db.coverages.push(coverage);
      const hospitalization: HospitalizationRead = {
        id: uuid(),
        patient_id: patient.id,
        status: body.requested_bed_id ? 'IN_PROGRESS' : 'PENDING_BED',
        admission_reason: body.admission_reason,
        admitted_at: body.requested_bed_id ? now() : null,
        discharged_at: null,
      };
      db.hospitalizations.push(hospitalization);
      const admission: AdmissionDashboardRead = {
        id: uuid(),
        patient_id: patient.id,
        patient,
        episode_id: uuid(),
        episode: {
          id: uuid(),
          patient_id: patient.id,
          episode_number: `EPI-${Date.now()}`,
          status: 'OPEN',
          reason: body.admission_reason,
          opened_at: now(),
          closed_at: null,
        },
        hospitalization_id: hospitalization.id,
        coverage_id: coverage?.id ?? body.coverage_id ?? null,
        coverage: coverage ?? null,
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
        presumptive_diagnosis: body.presumptive_diagnosis ?? null,
        notes: body.notes ?? null,
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
      const body = JSON.parse(config.data);
      const bed = db.beds.find((b) => b.id === body.bed_id);
      if (!bed) {
        return Promise.reject({ response: { status: 422, data: { detail: 'Bed not found' } }, config });
      }
      bed.status = 'OCCUPIED' as BedStatus;
      const hosp = db.hospitalizations.find((h) => h.id === hospId);
      if (hosp) {
        hosp.status = 'IN_PROGRESS' as HospitalizationStatus;
        hosp.admitted_at = now();
        const patient = db.patients.find((p) => p.id === hosp.patient_id);
        bed.patient = patient ?? null;
      }
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
        status: 'OCCUPIED' as BedStatus,
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
        assignment.ended_at = now();
        const bed = db.beds.find((b) => b.id === assignment.bed_id);
        if (bed) {
          bed.status = 'PENDING_CLEANING' as BedStatus;
          bed.patient = null;
        }
        const hosp = db.hospitalizations.find((h) => h.id === hospId);
        if (hosp) {
          hosp.status = 'CLINICALLY_DISCHARGED' as HospitalizationStatus;
          hosp.discharged_at = now();
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
