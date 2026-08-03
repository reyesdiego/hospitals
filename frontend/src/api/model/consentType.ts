export type ConsentType = typeof ConsentType[keyof typeof ConsentType];

export const ConsentType = {
  GENERAL_ADMISSION: 'GENERAL_ADMISSION',
  DATA_PROCESSING: 'DATA_PROCESSING',
  PROCEDURE: 'PROCEDURE',
  ANESTHESIA: 'ANESTHESIA',
  TRANSFER: 'TRANSFER',
} as const;
