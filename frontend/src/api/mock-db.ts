import type {
  AdmissionDashboardRead,
  ChargeItemRead,
  HealthPlanRead,
  HospitalizationPracticeRead,
  MedicalPracticeRead,
  MedicalPracticeTariffRead,
  PayerRead,
  AdmissionRead,
  AuthorizationRead,
  BedReservationRead,
  BedStatusHistoryRead,
  CareTeamRead,
  DischargePlanRead,
  DischargeRead,
  HospitalizationEventRead,
  ProfessionalRead,
  ServiceAssignmentRead,
  SpecialtyRead,
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

export const STORAGE_KEY = 'hosp_mock_db_v2';

export type MockDB = {
  patients: PatientRead[];
  facilities: FacilityRead[];
  beds: BedRead[];
  rooms: RoomRead[];
  services: ServiceRead[];
  hospitalizations: HospitalizationRead[];
  bedAssignments: BedAssignmentRead[];
  coverages: PatientCoverageRead[];
  payers: PayerRead[];
  healthPlans: HealthPlanRead[];
  practices: MedicalPracticeRead[];
  practiceTariffs: MedicalPracticeTariffRead[];
  hospitalizationPractices: HospitalizationPracticeRead[];
  chargeItems: ChargeItemRead[];
  admissions: AdmissionDashboardRead[];
  specialties: SpecialtyRead[];
  professionals: ProfessionalRead[];
  authorizations: AuthorizationRead[];
  bedReservations: BedReservationRead[];
  bedStatusHistory: BedStatusHistoryRead[];
  serviceAssignments: ServiceAssignmentRead[];
  careTeams: CareTeamRead[];
  dischargePlans: DischargePlanRead[];
  discharges: DischargeRead[];
  events: HospitalizationEventRead[];
};

export function uuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function now(): string {
  return new Date().toISOString();
}

export function toAdmissionRead(admission: AdmissionDashboardRead): AdmissionRead {
  const read: Partial<AdmissionDashboardRead> = { ...admission };
  delete read.patient;
  delete read.episode;
  delete read.coverage;
  delete read.consents;
  return read as AdmissionRead;
}

export function admissionWithEffectiveStatus(
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

export function seed(): MockDB {
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

  const payers: PayerRead[] = [
    { id: 'pay-001', name: 'OSDE', code: 'OSDE', tax_id: '30-54666577-0', created_at: '2025-01-01T08:00:00Z' },
    { id: 'pay-002', name: 'Swiss Medical', code: 'SMG', tax_id: null, created_at: '2025-01-01T08:00:00Z' },
    { id: 'pay-003', name: 'PAMI', code: 'PAMI', tax_id: null, created_at: '2025-01-01T08:00:00Z' },
  ];

  const healthPlans: HealthPlanRead[] = [
    { id: 'plan-001', payer_id: 'pay-001', name: '210', code: '210', created_at: '2025-01-01T08:00:00Z' },
    { id: 'plan-002', payer_id: 'pay-001', name: '310', code: '310', created_at: '2025-01-01T08:00:00Z' },
    { id: 'plan-003', payer_id: 'pay-002', name: 'SMG20', code: 'SMG20', created_at: '2025-01-01T08:00:00Z' },
  ];

  // Datos de demostracion: codigos con la forma del nomenclador, no una copia oficial.
  const practices: MedicalPracticeRead[] = [
    {
      id: 'prac-001',
      nomenclador: 'NACIONAL',
      code: '42.01.01',
      name: 'Consulta en consultorio',
      description: null,
      chapter: 'CONSULTAS',
      practice_type: 'CONSULTA',
      setting: 'AMBULATORIO',
      galeno_units: '40.00',
      expense_units: '10.00',
      anesthesia_units: '0.00',
      biochemical_units: '0.00',
      radiology_units: '0.00',
      requires_authorization: false,
      requires_consent: false,
      is_active: true,
      valid_from: '2026-01-01',
      valid_until: null,
      notes: null,
      created_at: '2026-01-01T08:00:00Z',
    },
    {
      id: 'prac-002',
      nomenclador: 'NACIONAL',
      code: '15.01.02',
      name: 'Colecistectomia videolaparoscopica',
      description: 'Incluye honorarios de cirujano, ayudante e instrumentacion.',
      chapter: 'CIRUGIA',
      practice_type: 'CIRUGIA',
      setting: 'INTERNACION',
      galeno_units: '320.00',
      expense_units: '180.00',
      anesthesia_units: '90.00',
      biochemical_units: '0.00',
      radiology_units: '0.00',
      requires_authorization: true,
      requires_consent: true,
      is_active: true,
      valid_from: '2026-01-01',
      valid_until: null,
      notes: null,
      created_at: '2026-01-01T08:00:00Z',
    },
    {
      id: 'prac-003',
      nomenclador: 'NBU',
      code: '66.01.01',
      name: 'Hemograma completo',
      description: null,
      chapter: 'LABORATORIO',
      practice_type: 'LABORATORIO',
      setting: 'AMBOS',
      galeno_units: '0.00',
      expense_units: '0.00',
      anesthesia_units: '0.00',
      biochemical_units: '12.00',
      radiology_units: '0.00',
      requires_authorization: false,
      requires_consent: false,
      is_active: true,
      valid_from: '2026-01-01',
      valid_until: null,
      notes: null,
      created_at: '2026-01-01T08:00:00Z',
    },
    {
      id: 'prac-004',
      nomenclador: 'NACIONAL',
      code: '34.02.01',
      name: 'Radiografia de torax frente',
      description: null,
      chapter: 'DIAGNOSTICO_POR_IMAGENES',
      practice_type: 'IMAGENES',
      setting: 'AMBOS',
      galeno_units: '15.00',
      expense_units: '25.00',
      anesthesia_units: '0.00',
      biochemical_units: '0.00',
      radiology_units: '30.00',
      requires_authorization: false,
      requires_consent: false,
      is_active: true,
      valid_from: '2026-01-01',
      valid_until: null,
      notes: null,
      created_at: '2026-01-01T08:00:00Z',
    },
    {
      id: 'prac-005',
      nomenclador: 'PROPIO',
      code: 'INT-DIA-CLM',
      name: 'Dia de internacion en clinica medica',
      description: 'Modulo institucional por dia de cama.',
      chapter: 'INTERNACION',
      practice_type: 'MODULO',
      setting: 'INTERNACION',
      galeno_units: '0.00',
      expense_units: '0.00',
      anesthesia_units: '0.00',
      biochemical_units: '0.00',
      radiology_units: '0.00',
      requires_authorization: true,
      requires_consent: false,
      is_active: true,
      valid_from: '2026-01-01',
      valid_until: null,
      notes: null,
      created_at: '2026-01-01T08:00:00Z',
    },
  ];

  const practiceTariffs: MedicalPracticeTariffRead[] = [
    {
      id: 'tar-001',
      practice_id: 'prac-001',
      payer_id: null,
      health_plan_id: null,
      unit_value: '100.00',
      professional_fee: '4000.00',
      expense_amount: '1000.00',
      total_amount: '5000.00',
      coinsurance: '0.00',
      currency: 'ARS',
      valid_from: '2026-01-01',
      valid_until: null,
      notes: 'Valor institucional para paciente particular',
      created_at: '2026-01-01T08:00:00Z',
    },
    {
      id: 'tar-002',
      practice_id: 'prac-001',
      payer_id: 'pay-001',
      health_plan_id: null,
      unit_value: '120.00',
      professional_fee: '4800.00',
      expense_amount: '1200.00',
      total_amount: '6000.00',
      coinsurance: '1500.00',
      currency: 'ARS',
      valid_from: '2026-01-01',
      valid_until: null,
      notes: null,
      created_at: '2026-01-01T08:00:00Z',
    },
    {
      id: 'tar-003',
      practice_id: 'prac-001',
      payer_id: 'pay-001',
      health_plan_id: 'plan-002',
      unit_value: '150.00',
      professional_fee: '6000.00',
      expense_amount: '1500.00',
      total_amount: '7500.00',
      coinsurance: '0.00',
      currency: 'ARS',
      valid_from: '2026-01-01',
      valid_until: null,
      notes: 'El plan 310 no tiene coseguro',
      created_at: '2026-01-01T08:00:00Z',
    },
    {
      id: 'tar-004',
      practice_id: 'prac-005',
      payer_id: 'pay-003',
      health_plan_id: null,
      unit_value: null,
      professional_fee: '0.00',
      expense_amount: '0.00',
      total_amount: '185000.00',
      coinsurance: '0.00',
      currency: 'ARS',
      valid_from: '2026-01-01',
      valid_until: null,
      notes: 'Modulo cerrado por dia de internacion',
      created_at: '2026-01-01T08:00:00Z',
    },
  ];

  const coverages: PatientCoverageRead[] = [
    {
      id: 'cov-001',
      patient_id: 'pat-001',
      payer_id: null,
      health_plan_id: null,
      payer_name: 'OSDE',
      plan_name: '210',
      member_number: '998877',
      authorization_required: true,
      valid_from: null,
      valid_until: null,
      status: 'ACTIVE',
      created_at: '2025-07-20T13:30:00Z',
    },
  ];

  const hospitalizations: HospitalizationRead[] = [
    {
      id: 'hosp-001',
      patient_id: 'pat-001',
      episode_id: 'epi-001',
      facility_id: 'fac-001',
      admission_type: 'EMERGENCY',
      status: 'IN_PROGRESS' as HospitalizationStatus,
      admission_reason: 'Dolor toracico agudo - evaluacion cardiaca',
      admitted_at: '2025-07-20T14:30:00Z',
      clinically_discharged_at: null,
      physically_departed_at: null,
      administratively_discharged_at: null,
      closed_at: null,
    },
    {
      id: 'hosp-002',
      patient_id: 'pat-002',
      episode_id: null,
      facility_id: 'fac-001',
      admission_type: 'SCHEDULED',
      status: 'PENDING_BED' as HospitalizationStatus,
      admission_reason: 'Post-operatorio - observacion',
      admitted_at: null,
      clinically_discharged_at: null,
      physically_departed_at: null,
      administratively_discharged_at: null,
      closed_at: null,
    },
  ];

  const bedAssignments: BedAssignmentRead[] = [
    {
      id: 'asg-001',
      hospitalization_id: 'hosp-001',
      bed_id: 'bed-002',
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
        facility_id: 'fac-001',
        episode_number: 'EPI-20250720143000-DEMO',
        status: 'OPEN',
        reason: 'Dolor toracico agudo - evaluacion cardiaca',
        opened_at: '2025-07-20T14:30:00Z',
        closed_at: null,
      },
      hospitalization_id: 'hosp-001',
      coverage_id: 'cov-001',
      coverage: coverages[0],
      facility_id: 'fac-001',
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
      responsible_physician_id: null,
      presumptive_diagnosis: 'Sindrome coronario a descartar',
      notes: null,
      requested_at: '2025-07-20T14:30:00Z',
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

  admissions.push({
    id: 'adm-002',
    patient_id: 'pat-002',
    patient: patients[1],
    episode_id: null,
    episode: null,
    hospitalization_id: 'hosp-002',
    coverage_id: null,
    coverage: null,
    facility_id: 'fac-001',
    requesting_service_id: 'srv-002',
    requested_bed_id: null,
    origin: 'SCHEDULED_SURGERY',
    admission_type: 'SCHEDULED',
    status: 'PENDING_BED' as AdmissionStatus,
    identity_validated: true,
    duplicate_checked: true,
    authorization_status: 'NOT_REQUIRED' as AuthorizationStatus,
    authorization_number: null,
    responsible_contact_name: 'Carlos Garcia',
    responsible_contact_phone: '+54 11 5555-2020',
    responsible_contact_relationship: 'Hermano',
    admission_reason: 'Post-operatorio - observacion',
    responsible_physician: 'Dr. Sosa',
    responsible_physician_id: 'pro-002',
    presumptive_diagnosis: null,
    notes: null,
    requested_at: '2025-07-21T09:00:00Z',
    admitted_at: null,
    administrative_discharged_at: null,
    consents: [],
    created_at: '2025-07-21T09:00:00Z',
  });

  const specialties: SpecialtyRead[] = [
    { id: 'spe-001', name: 'Cardiologia', code: 'CAR', created_at: '2025-01-01T08:00:00Z' },
    { id: 'spe-002', name: 'Clinica medica', code: 'CLM', created_at: '2025-01-01T08:00:00Z' },
  ];

  const professionals: ProfessionalRead[] = [
    {
      id: 'pro-001',
      first_name: 'Laura',
      last_name: 'Alvarez',
      document_type: 'DNI',
      document_number: '20111222',
      email: 'laura.alvarez@hospital.test',
      phone: '+54 11 4444-1010',
      specialties: [
        {
          id: 'psp-001',
          specialty_id: 'spe-001',
          specialty: specialties[0],
          license_number: 'MN-10011',
          created_at: '2025-01-01T08:00:00Z',
        },
      ],
      created_at: '2025-01-01T08:00:00Z',
    },
    {
      id: 'pro-002',
      first_name: 'Diego',
      last_name: 'Sosa',
      document_type: 'DNI',
      document_number: '20111333',
      email: null,
      phone: null,
      specialties: [
        {
          id: 'psp-002',
          specialty_id: 'spe-002',
          specialty: specialties[1],
          license_number: 'MN-10022',
          created_at: '2025-01-01T08:00:00Z',
        },
      ],
      created_at: '2025-01-01T08:00:00Z',
    },
  ];

  const serviceAssignments: ServiceAssignmentRead[] = [
    {
      id: 'sas-001',
      hospitalization_id: 'hosp-001',
      service_id: 'srv-001',
      started_at: '2025-07-20T14:30:00Z',
      ended_at: null,
      reason: 'Servicio responsable inicial',
      assigned_by: null,
    },
  ];

  const careTeams: CareTeamRead[] = [
    {
      id: 'ctm-001',
      hospitalization_id: 'hosp-001',
      members: [
        {
          id: 'ctu-001',
          care_team_id: 'ctm-001',
          practitioner_id: 'pro-001',
          role: 'ATTENDING_PHYSICIAN',
          started_at: '2025-07-20T14:30:00Z',
          ended_at: null,
          notes: 'Medico responsable de la admision',
        },
      ],
    },
    { id: 'ctm-002', hospitalization_id: 'hosp-002', members: [] },
  ];

  const bedStatusHistory: BedStatusHistoryRead[] = [
    {
      id: 'bsh-001',
      bed_id: 'bed-002',
      previous_status: 'AVAILABLE',
      new_status: 'OCCUPIED',
      changed_at: '2025-07-20T15:00:00Z',
      changed_by: null,
      reason: 'Ingreso del paciente',
    },
  ];

  const authorizations: AuthorizationRead[] = [
    {
      id: 'aut-001',
      patient_id: 'pat-001',
      admission_id: 'adm-001',
      hospitalization_id: 'hosp-001',
      patient_coverage_id: 'cov-001',
      authorization_type: 'ADMISSION',
      authorization_number: 'AUT-4455',
      status: 'AUTHORIZED',
      requested_at: '2025-07-20T14:35:00Z',
      requested_by: 'Admision',
      resolved_at: '2025-07-20T14:50:00Z',
      authorized_at: '2025-07-20T14:50:00Z',
      valid_from: null,
      valid_until: null,
      notes: null,
      created_at: '2025-07-20T14:35:00Z',
    },
  ];

  const chargeItems: ChargeItemRead[] = [
    {
      id: 'chg-001',
      account_id: 'acc-hosp-001',
      practice_id: 'prac-001',
      practice_code: '42.01.01',
      category: 'PROFESSIONAL_FEE',
      description: '42.01.01 - Consulta en consultorio',
      quantity: '1.000',
      unit_price: '6000.00',
      amount: '6000.00',
      charged_at: '2025-07-20T16:00:00Z',
      recorded_by: null,
      notes: 'Evaluacion cardiologica al ingreso',
      status: 'ACTIVE',
      voided_at: null,
      voided_by: null,
      void_reason: null,
    },
  ];

  const hospitalizationPractices: HospitalizationPracticeRead[] = [
    {
      id: 'hpr-001',
      hospitalization_id: 'hosp-001',
      practice_id: 'prac-001',
      practice_code: '42.01.01',
      practice_name: 'Consulta en consultorio',
      prescribed_by_id: 'pro-001',
      performed_by_id: 'pro-001',
      service_id: 'srv-001',
      charge_item_id: 'chg-001',
      status: 'PERFORMED',
      quantity: '1.000',
      prescribed_at: '2025-07-20T15:30:00Z',
      performed_at: '2025-07-20T16:00:00Z',
      cancelled_at: null,
      indication: 'Evaluacion cardiologica al ingreso',
      notes: null,
      created_at: '2025-07-20T15:30:00Z',
      charge: chargeItems[0],
    },
    {
      id: 'hpr-002',
      hospitalization_id: 'hosp-001',
      practice_id: 'prac-004',
      practice_code: '34.02.01',
      practice_name: 'Radiografia de torax frente',
      prescribed_by_id: 'pro-002',
      performed_by_id: null,
      service_id: 'srv-001',
      charge_item_id: null,
      status: 'REQUESTED',
      quantity: '1.000',
      prescribed_at: '2025-07-21T09:15:00Z',
      performed_at: null,
      cancelled_at: null,
      indication: 'Control evolutivo',
      notes: null,
      created_at: '2025-07-21T09:15:00Z',
      charge: null,
    },
  ];

  const events: HospitalizationEventRead[] = [
    {
      id: 'evt-001',
      event_type: 'HOSPITALIZATION_CREATED',
      hospitalization_id: 'hosp-001',
      admission_id: 'adm-001',
      bed_id: null,
      patient_id: 'pat-001',
      occurred_at: '2025-07-20T14:30:00Z',
      actor: null,
      details: null,
    },
    {
      id: 'evt-002',
      event_type: 'BED_ASSIGNED',
      hospitalization_id: 'hosp-001',
      admission_id: 'adm-001',
      bed_id: 'bed-002',
      patient_id: 'pat-001',
      occurred_at: '2025-07-20T15:00:00Z',
      actor: null,
      details: null,
    },
  ];

  return {
    patients,
    facilities,
    payers,
    healthPlans,
    practices,
    practiceTariffs,
    hospitalizationPractices,
    chargeItems,
    beds,
    rooms,
    services,
    hospitalizations,
    bedAssignments,
    coverages,
    admissions,
    specialties,
    professionals,
    authorizations,
    bedReservations: [],
    bedStatusHistory,
    serviceAssignments,
    careTeams,
    dischargePlans: [],
    discharges: [],
    events,
  };
}

export function loadDB(): MockDB {
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
        payers: parsed.payers ?? seeded.payers,
        healthPlans: parsed.healthPlans ?? seeded.healthPlans,
        practices: parsed.practices ?? seeded.practices,
        practiceTariffs: parsed.practiceTariffs ?? seeded.practiceTariffs,
        hospitalizationPractices:
          parsed.hospitalizationPractices ?? seeded.hospitalizationPractices,
        chargeItems: parsed.chargeItems ?? seeded.chargeItems,
        admissions: parsed.admissions ?? seeded.admissions,
        specialties: parsed.specialties ?? seeded.specialties,
        professionals: parsed.professionals ?? seeded.professionals,
        authorizations: parsed.authorizations ?? seeded.authorizations,
        bedReservations: parsed.bedReservations ?? seeded.bedReservations,
        bedStatusHistory: parsed.bedStatusHistory ?? seeded.bedStatusHistory,
        serviceAssignments: parsed.serviceAssignments ?? seeded.serviceAssignments,
        careTeams: parsed.careTeams ?? seeded.careTeams,
        dischargePlans: parsed.dischargePlans ?? seeded.dischargePlans,
        discharges: parsed.discharges ?? seeded.discharges,
        events: parsed.events ?? seeded.events,
      };
    } catch {
      // fall through to seed
    }
  }
  const db = seed();
  saveDB(db);
  return db;
}

export function saveDB(db: MockDB) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(db));
}

