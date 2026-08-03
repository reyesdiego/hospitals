import type { RoomStatus } from './roomStatus';

export interface RoomRead {
  id: string;
  facility_id: string;
  code: string;
  ward: string;
  status: RoomStatus;
  created_at: string;
}
