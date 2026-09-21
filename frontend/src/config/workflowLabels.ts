import type {
  AdmissionOrigin,
  AdmissionStatus,
  AdmissionType,
  AuthorizationState,
  AuthorizationStatus,
  AuthorizationType,
  BedReservationStatus,
  CareTeamRole,
  DischargeDestination,
  DischargePlanStatus,
  ConsentType,
  DischargeType,
  AccountStatus,
  ChargeCategory,
  ChargeItemStatus,
  HospitalizationEventType,
  PaymentMethod,
  PracticeOrderStatus,
  ResponsibleParty,
} from '@/api/model';

export const RESERVATION_STATUS_LABELS: Record<BedReservationStatus, string> = {
  ACTIVE: 'Activa',
  COMPLETED: 'Confirmada',
  CANCELLED: 'Cancelada',
  EXPIRED: 'Vencida',
};

export const RESERVATION_STATUS_COLORS: Record<BedReservationStatus, string> = {
  ACTIVE: 'bg-amber-50 text-amber-700',
  COMPLETED: 'bg-emerald-50 text-emerald-700',
  CANCELLED: 'bg-slate-100 text-slate-600',
  EXPIRED: 'bg-red-50 text-red-700',
};

export const CARE_TEAM_ROLE_LABELS: Record<CareTeamRole, string> = {
  ATTENDING_PHYSICIAN: 'Medico de cabecera',
  SPECIALIST: 'Especialista',
  RESIDENT: 'Residente',
  NURSE: 'Enfermeria',
  OTHER: 'Otro',
};

export const DISCHARGE_DESTINATION_LABELS: Record<DischargeDestination, string> = {
  HOME: 'Domicilio',
  OTHER_FACILITY: 'Otra institucion',
  HOME_CARE: 'Internacion domiciliaria',
  REHABILITATION: 'Rehabilitacion',
  OTHER: 'Otro',
};

export const DISCHARGE_PLAN_STATUS_LABELS: Record<DischargePlanStatus, string> = {
  PLANNED: 'Planificada',
  CONFIRMED: 'Confirmada',
  COMPLETED: 'Cumplida',
  CANCELLED: 'Cancelada',
};

export const DISCHARGE_TYPE_LABELS: Record<DischargeType, string> = {
  MEDICAL: 'Alta medica',
  VOLUNTARY: 'Alta voluntaria',
  TRANSFER: 'Derivacion',
  DECEASED: 'Fallecimiento',
  ABSCONDED: 'Retiro sin alta',
  OTHER: 'Otro',
};

export const EVENT_TYPE_LABELS: Record<HospitalizationEventType, string> = {
  ADMISSION_REQUESTED: 'Solicitud de admision',
  ADMISSION_AUTHORIZED: 'Admision autorizada',
  ADMISSION_REJECTED: 'Admision rechazada',
  HOSPITALIZATION_CREATED: 'Internacion creada',
  SERVICE_ASSIGNED: 'Servicio responsable asignado',
  CARE_TEAM_MEMBER_ASSIGNED: 'Integrante agregado al equipo',
  CARE_TEAM_MEMBER_ENDED: 'Integrante finalizo su participacion',
  BED_RESERVED: 'Cama reservada',
  BED_RESERVATION_CANCELLED: 'Reserva cancelada',
  BED_RESERVATION_EXPIRED: 'Reserva vencida',
  BED_ASSIGNED: 'Ingreso a la cama',
  PATIENT_TRANSFERRED: 'Paciente trasladado',
  BED_RELEASED: 'Cama liberada',
  DIAGNOSIS_RECORDED: 'Diagnostico asentado',
  DIAGNOSIS_REMOVED: 'Diagnostico quitado',
  PRACTICE_ORDERED: 'Practica indicada',
  PRACTICE_PERFORMED: 'Practica realizada',
  PRACTICE_CANCELLED: 'Practica anulada',
  DISCHARGE_PLANNED: 'Alta planificada',
  CLINICAL_DISCHARGE_COMPLETED: 'Alta clinica',
  PATIENT_PHYSICALLY_DEPARTED: 'Salida fisica del paciente',
  BED_CLEANING_STARTED: 'Limpieza iniciada',
  BED_AVAILABLE: 'Cama disponible',
  BED_STATUS_CHANGED: 'Cambio de estado de la cama',
  ADMINISTRATIVE_DISCHARGE_COMPLETED: 'Alta administrativa',
  CHARGE_ITEM_VOIDED: 'Cargo anulado',
  PAYMENT_REGISTERED: 'Pago registrado',
  PAYMENT_VOIDED: 'Pago anulado',
  ACCOUNT_READY_FOR_REVIEW: 'Cuenta lista para auditoria',
  HOSPITALIZATION_CLOSED: 'Internacion cerrada',
  HOSPITALIZATION_CANCELLED: 'Internacion cancelada',
  POST_DISCHARGE_CHANGE: 'Cambio posterior al alta medica',
};

export const ADMISSION_ORIGIN_LABELS: Record<AdmissionOrigin, string> = {
  EMERGENCY_ROOM: 'Guardia',
  OUTPATIENT_CLINIC: 'Consultorio externo',
  SCHEDULED_SURGERY: 'Cirugia programada',
  EXTERNAL_REFERRAL: 'Derivacion externa',
  HOME_HOSPITALIZATION: 'Internacion domiciliaria',
  SPECIAL_CARE_UNIT: 'Unidad de cuidados especiales',
  SCHEDULED_MEDICAL_ORDER: 'Orden medica programada',
};

export const ADMISSION_TYPE_LABELS: Record<AdmissionType, string> = {
  PRE_ADMISSION: 'Pre-admision',
  SCHEDULED: 'Programada',
  EMERGENCY: 'Urgencia',
};

export const ADMISSION_STATUS_LABELS: Record<AdmissionStatus, string> = {
  PRE_ADMITTED: 'Pre-admitida',
  PENDING_AUTHORIZATION: 'Pendiente de autorizacion',
  PENDING_BED: 'Pendiente de cama',
  ADMITTED: 'Ingresado',
  REJECTED: 'Rechazada',
  ADMINISTRATIVE_DISCHARGE: 'Alta administrativa',
  CANCELLED: 'Cancelada',
};

export const ADMISSION_STATUS_COLORS: Record<AdmissionStatus, string> = {
  PRE_ADMITTED: 'bg-slate-100 text-slate-600',
  PENDING_AUTHORIZATION: 'bg-amber-50 text-amber-700',
  PENDING_BED: 'bg-cyan-50 text-cyan-700',
  ADMITTED: 'bg-emerald-50 text-emerald-700',
  REJECTED: 'bg-red-50 text-red-700',
  ADMINISTRATIVE_DISCHARGE: 'bg-violet-50 text-violet-700',
  CANCELLED: 'bg-slate-100 text-slate-600',
};

export const COVERAGE_AUTHORIZATION_LABELS: Record<AuthorizationStatus, string> = {
  NOT_REQUIRED: 'No requiere autorizacion',
  PENDING: 'Autorizacion pendiente',
  AUTHORIZED: 'Autorizada',
  REJECTED: 'Autorizacion rechazada',
};

export const AUTHORIZATION_TYPE_LABELS: Record<AuthorizationType, string> = {
  ADMISSION: 'Internacion',
  EXTENSION: 'Prorroga',
  PROCEDURE: 'Practica',
  TRANSFER: 'Derivacion',
  OTHER: 'Otra',
};

export const AUTHORIZATION_STATE_LABELS: Record<AuthorizationState, string> = {
  REQUESTED: 'Solicitada',
  PENDING: 'Pendiente',
  AUTHORIZED: 'Autorizada',
  REJECTED: 'Rechazada',
  EXPIRED: 'Vencida',
  CANCELLED: 'Cancelada',
};

export const AUTHORIZATION_STATE_COLORS: Record<AuthorizationState, string> = {
  REQUESTED: 'bg-slate-100 text-slate-600',
  PENDING: 'bg-amber-50 text-amber-700',
  AUTHORIZED: 'bg-emerald-50 text-emerald-700',
  REJECTED: 'bg-red-50 text-red-700',
  EXPIRED: 'bg-orange-50 text-orange-700',
  CANCELLED: 'bg-slate-100 text-slate-600',
};

export const CONSENT_TYPE_LABELS: Record<ConsentType, string> = {
  GENERAL_ADMISSION: 'Admision general',
  DATA_PROCESSING: 'Tratamiento de datos',
  PROCEDURE: 'Procedimiento',
  ANESTHESIA: 'Anestesia',
  TRANSFER: 'Traslado',
};

export const PRACTICE_ORDER_STATUS_LABELS: Record<PracticeOrderStatus, string> = {
  REQUESTED: 'Indicada',
  PERFORMED: 'Realizada',
  CANCELLED: 'Anulada',
};

export const PRACTICE_ORDER_STATUS_COLORS: Record<PracticeOrderStatus, string> = {
  REQUESTED: 'bg-amber-50 text-amber-700',
  PERFORMED: 'bg-emerald-50 text-emerald-700',
  CANCELLED: 'bg-slate-100 text-slate-600',
};

export const ACCOUNT_STATUS_LABELS: Record<AccountStatus, string> = {
  OPEN: 'Abierta',
  READY_FOR_REVIEW: 'Lista para auditoria',
  CLOSED: 'Cerrada',
  CANCELLED: 'Anulada',
};

export const ACCOUNT_STATUS_COLORS: Record<AccountStatus, string> = {
  OPEN: 'bg-teal-50 text-teal-700',
  READY_FOR_REVIEW: 'bg-amber-50 text-amber-700',
  CLOSED: 'bg-slate-100 text-slate-600',
  CANCELLED: 'bg-red-50 text-red-700',
};

export const CHARGE_CATEGORY_LABELS: Record<ChargeCategory, string> = {
  HOSPITALIZATION_DAY: 'Dia de internacion',
  INTENSIVE_CARE_DAY: 'Dia de terapia intensiva',
  MEDICATION: 'Medicamentos',
  LABORATORY: 'Laboratorio',
  IMAGING: 'Imagenes',
  PROCEDURE: 'Procedimiento',
  SUPPLY: 'Insumos',
  PROFESSIONAL_FEE: 'Honorarios',
  OTHER: 'Otros',
};

export const RESPONSIBLE_PARTY_LABELS: Record<ResponsibleParty, string> = {
  PAYER: 'Cobertura',
  PATIENT: 'Paciente',
};

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  CASH: 'Efectivo',
  DEBIT_CARD: 'Tarjeta de debito',
  CREDIT_CARD: 'Tarjeta de credito',
  BANK_TRANSFER: 'Transferencia',
  CHECK: 'Cheque',
  OTHER: 'Otro',
};

export const CHARGE_ITEM_STATUS_LABELS: Record<ChargeItemStatus, string> = {
  ACTIVE: 'Vigente',
  VOID: 'Anulado',
};
