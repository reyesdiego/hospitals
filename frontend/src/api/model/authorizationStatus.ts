export type AuthorizationStatus = typeof AuthorizationStatus[keyof typeof AuthorizationStatus];

export const AuthorizationStatus = {
  NOT_REQUIRED: 'NOT_REQUIRED',
  PENDING: 'PENDING',
  AUTHORIZED: 'AUTHORIZED',
  REJECTED: 'REJECTED',
} as const;
