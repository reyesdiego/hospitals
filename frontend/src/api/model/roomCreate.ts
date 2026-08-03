import type { RoomStatus } from './roomStatus';

export interface RoomCreate {
  facility_id: string;
  code: string;
  ward: string;
  status?: RoomStatus;
}
