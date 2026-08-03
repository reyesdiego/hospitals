import type { EpisodeStatus } from './episodeStatus';

export interface EpisodeRead {
  id: string;
  patient_id: string;
  episode_number: string;
  status: EpisodeStatus;
  reason: string;
  opened_at: string;
  closed_at: string | null;
}
