import type { BedRead, PatientRead } from '@/api/model';
import { BedStatusBadge } from '@/components/StatusBadges';
import { formatDateTime } from '@/utils/format';

function calculateAge(birthDate: string | null | undefined): number | null {
  if (!birthDate) return null;

  const [year, month, day] = birthDate.split('-').map(Number);
  if (!year || !month || !day) return null;

  const today = new Date();
  let age = today.getFullYear() - year;
  const birthdayPassed =
    today.getMonth() + 1 > month || (today.getMonth() + 1 === month && today.getDate() >= day);

  if (!birthdayPassed) age -= 1;
  return age >= 0 ? age : null;
}

function patientName(patient: PatientRead): string {
  return `${patient.first_name} ${patient.last_name}`.trim();
}

export function BedCard({
  bed,
  compact = false,
  showWard = false,
}: {
  bed: BedRead;
  compact?: boolean;
  showWard?: boolean;
}) {
  const age = calculateAge(bed.patient?.birth_date);
  const patientDetails = bed.patient
    ? age === null
      ? 'Edad no registrada'
      : `${age} años`
    : 'Sin paciente asignado';

  return (
    <div
      className={`rounded-lg border border-slate-100 bg-slate-50/50 transition-colors hover:bg-slate-50 ${
        compact ? 'p-3' : 'p-4'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={`${compact ? 'text-sm' : 'text-base'} font-bold text-slate-700`}>
            {bed.code}
          </p>
          <p className="truncate text-xs text-slate-400">
            {showWard ? `${bed.ward} - ` : ''}Hab. {bed.room}
          </p>
        </div>
        <BedStatusBadge status={bed.status} />
      </div>

      {bed.patient ? (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <p className="truncate text-sm font-semibold text-slate-700">
            {patientName(bed.patient)}
          </p>
          <p className="mt-0.5 truncate text-xs text-slate-400">{patientDetails}</p>
        </div>
      ) : bed.reserved_for ? (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <p className="truncate text-sm font-semibold text-amber-700">
            Reservada: {patientName(bed.reserved_for)}
          </p>
          <p className="mt-0.5 truncate text-xs text-amber-600">
            {bed.reservation_expires_at
              ? `Vence ${formatDateTime(bed.reservation_expires_at)}`
              : 'Sin vencimiento'}
          </p>
        </div>
      ) : null}
    </div>
  );
}
