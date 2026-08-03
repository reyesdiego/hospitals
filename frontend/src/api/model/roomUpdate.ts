import type { RoomStatus } from './roomStatus';

export interface RoomUpdate {
  facility_id: string;
  code: string;
  ward: string;
  status: RoomStatus;
}
