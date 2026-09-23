import type { HospitalizationStatus } from '@/api/model';

/** Con el alta medica dada la internacion deja de recibir cambios, y sigue asi despues. */
export const POST_DISCHARGE_STATUSES: HospitalizationStatus[] = [
  'CLINICALLY_DISCHARGED',
  'ADMINISTRATIVELY_DISCHARGED',
  'CLOSED',
];

/** Orden medica programada: la cama puede estar reservada pero el paciente no llego, asi
 * que no hay nada clinico ni cargos que hacer hasta confirmar su ingreso. */
export const isAwaitingArrival = (status: HospitalizationStatus): boolean =>
  status === 'AWAITING_ARRIVAL';

export const isPostDischarge = (status: HospitalizationStatus): boolean =>
  POST_DISCHARGE_STATUSES.includes(status);
