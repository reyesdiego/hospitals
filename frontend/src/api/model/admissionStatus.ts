export type AdmissionStatus = typeof AdmissionStatus[keyof typeof AdmissionStatus];

export const AdmissionStatus = {
  PRE_ADMITTED: 'PRE_ADMITTED',
  PENDING_AUTHORIZATION: 'PENDING_AUTHORIZATION',
  PENDING_BED: 'PENDING_BED',
  ADMITTED: 'ADMITTED',
  ADMINISTRATIVE_DISCHARGE: 'ADMINISTRATIVE_DISCHARGE',
  CANCELLED: 'CANCELLED',
} as const;
