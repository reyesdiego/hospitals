export type AdmissionType = typeof AdmissionType[keyof typeof AdmissionType];

export const AdmissionType = {
  PRE_ADMISSION: 'PRE_ADMISSION',
  SCHEDULED: 'SCHEDULED',
  EMERGENCY: 'EMERGENCY',
} as const;
