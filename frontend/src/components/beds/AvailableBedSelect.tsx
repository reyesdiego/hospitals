import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getBedWorkflow } from '@/api/endpoints/bed-workflow/bed-workflow';
import { getDefault } from '@/api/endpoints/default/default';
import type { BedRead } from '@/api/model';

/** Camas libres de todos los centros, agrupadas por centro: antes de ocupar la primera cama
 * al paciente se lo puede internar donde haya lugar. Elegir el centro solo acota la lista. */
export default function AvailableBedSelect({
  value,
  onChange,
  emptyLabel,
  excludeBedId,
  className,
}: {
  value: string;
  onChange: (bedId: string) => void;
  emptyLabel: string;
  excludeBedId?: string;
  className: string;
}) {
  const api = getDefault();
  const bedApi = getBedWorkflow();
  const [facilityId, setFacilityId] = useState('');

  const bedsQuery = useQuery({
    queryKey: ['beds-available', 'all'],
    queryFn: () => bedApi.searchAvailableBedsApiV1BedsAvailableGet(),
  });
  const facilitiesQuery = useQuery({
    queryKey: ['facilities'],
    queryFn: () => api.listFacilitiesApiV1FacilitiesGet(),
  });

  const beds = (bedsQuery.data ?? []).filter((bed) => bed.id !== excludeBedId);
  const facilities = facilitiesQuery.data ?? [];
  const facilityName = (id: string) =>
    facilities.find((facility) => facility.id === id)?.name ?? 'Centro sin nombre';
  // Solo los centros que tienen alguna cama libre.
  const facilityIds = [...new Set(beds.map((bed) => bed.facility_id))].sort((a, b) =>
    facilityName(a).localeCompare(facilityName(b)),
  );
  const shown = facilityId ? [facilityId] : facilityIds;
  const byFacility = (id: string) => beds.filter((bed) => bed.facility_id === id);
  const bedLabel = (bed: BedRead) => `${bed.code} - ${bed.ward} Hab. ${bed.room}`;

  return (
    <div className="grid gap-3 md:grid-cols-[200px_minmax(0,1fr)]">
      <select
        value={facilityId}
        onChange={(e) => {
          setFacilityId(e.target.value);
          // La cama elegida puede no ser del centro nuevo.
          const bed = beds.find((item) => item.id === value);
          if (e.target.value && bed && bed.facility_id !== e.target.value) onChange('');
        }}
        aria-label="Centro"
        className={className}
      >
        <option value="">Todos los centros ({beds.length} libres)</option>
        {facilityIds.map((id) => (
          <option key={id} value={id}>
            {facilityName(id)} ({byFacility(id).length})
          </option>
        ))}
      </select>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Cama"
        className={className}
      >
        <option value="">
          {bedsQuery.isLoading
            ? 'Buscando camas libres...'
            : beds.length === 0
              ? 'No hay camas libres en ningun centro'
              : emptyLabel}
        </option>
        {shown.map((id) => (
          <optgroup key={id} label={facilityName(id)}>
            {byFacility(id).map((bed) => (
              <option key={bed.id} value={bed.id}>
                {bedLabel(bed)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
