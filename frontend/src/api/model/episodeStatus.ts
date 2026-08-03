export type EpisodeStatus = typeof EpisodeStatus[keyof typeof EpisodeStatus];

export const EpisodeStatus = {
  OPEN: 'OPEN',
  CLOSED: 'CLOSED',
  CANCELLED: 'CANCELLED',
} as const;
