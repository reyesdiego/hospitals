import type { BedStatus, HospitalizationStatus } from '@/api/model';
import { Badge } from './ui';

const BED_STATUS_COLORS: Record<BedStatus, string> = {
  AVAILABLE: 'bg-emerald-50 text-emerald-700',
  RESERVED: 'bg-amber-50 text-amber-700',
  OCCUPIED: 'bg-rose-50 text-rose-700',
  PENDING_CLEANING: 'bg-orange-50 text-orange-700',
  BLOCKED: 'bg-slate-100 text-slate-600',
  MAINTENANCE: 'bg-red-50 text-red-700',
};

const BED_STATUS_LABELS: Record<BedStatus, string> = {
  AVAILABLE: 'Disponible',
  RESERVED: 'Reservada',
  OCCUPIED: 'Ocupada',
  PENDING_CLEANING: 'Limpieza',
  BLOCKED: 'Bloqueada',
  MAINTENANCE: 'Mantenimiento',
};

const HOSP_STATUS_COLORS: Record<HospitalizationStatus, string> = {
  PENDING_BED: 'bg-amber-50 text-amber-700',
  IN_PROGRESS: 'bg-teal-50 text-teal-700',
  CLINICALLY_DISCHARGED: 'bg-blue-50 text-blue-700',
  CLOSED: 'bg-slate-100 text-slate-600',
  CANCELLED: 'bg-red-50 text-red-700',
};

const HOSP_STATUS_LABELS: Record<HospitalizationStatus, string> = {
  PENDING_BED: 'Pendiente de cama',
  IN_PROGRESS: 'En curso',
  CLINICALLY_DISCHARGED: 'Alta clinica',
  CLOSED: 'Cerrada',
  CANCELLED: 'Cancelada',
};

export function BedStatusBadge({ status }: { status: BedStatus }) {
  return (
    <Badge status={BED_STATUS_LABELS[status]} color={BED_STATUS_COLORS[status]} />
  );
}

export function HospitalizationStatusBadge({ status }: { status: HospitalizationStatus }) {
  return (
    <Badge status={HOSP_STATUS_LABELS[status]} color={HOSP_STATUS_COLORS[status]} />
  );
}

export { BED_STATUS_LABELS, HOSP_STATUS_LABELS };
