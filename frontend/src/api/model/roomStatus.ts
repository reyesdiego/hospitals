export type RoomStatus = typeof RoomStatus[keyof typeof RoomStatus];

export const RoomStatus = {
  AVAILABLE: 'AVAILABLE',
  RESERVED: 'RESERVED',
  OCCUPIED: 'OCCUPIED',
  PENDING_CLEANING: 'PENDING_CLEANING',
  BLOCKED: 'BLOCKED',
  MAINTENANCE: 'MAINTENANCE',
} as const;
