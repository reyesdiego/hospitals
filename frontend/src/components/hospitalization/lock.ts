import type { HospitalizationStatus } from '@/api/model';

/** Con el alta medica dada la internacion deja de recibir cambios, y sigue asi despues. */
export const POST_DISCHARGE_STATUSES: HospitalizationStatus[] = [
  'CLINICALLY_DISCHARGED',
  'ADMINISTRATIVELY_DISCHARGED',
  'CLOSED',
];

export const isPostDischarge = (status: HospitalizationStatus): boolean =>
  POST_DISCHARGE_STATUSES.includes(status);
