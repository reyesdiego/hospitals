import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { ProfessionalRead } from '@/api/model';
import { ActionButton, inputClass } from '@/components/ui';
import { Search } from 'lucide-react';

/** Cuantos profesionales se ofrecen por busqueda. */
const SUGGESTIONS = 10;

function professionalLabel(professional: ProfessionalRead): string {
  return `${professional.last_name}, ${professional.first_name}`;
}

function professionalDetail(professional: ProfessionalRead): string {
  const specialties = (professional.specialties ?? []).map((item) => item.specialty.name);
  const license = professional.specialties?.[0]?.license_number;
  return [specialties.join(', '), license ? `Mat. ${license}` : null]
    .filter(Boolean)
    .join(' · ');
}

/** Buscador de profesionales: se escribe apellido, documento o especialidad y se elige de
 * las coincidencias, igual que el buscador de diagnosticos. El padron es chico y ya viene
 * cargado, asi que se filtra en memoria y no hay un pedido por tecla. */
export default function ProfessionalPicker({
  value,
  onSelect,
  placeholder = 'Buscar por apellido, documento o especialidad',
  emptyLabel = 'Sin registrar',
  disabled = false,
}: {
  value: string;
  onSelect: (professionalId: string) => void;
  placeholder?: string;
  emptyLabel?: string;
  disabled?: boolean;
}) {
  const api = getDefault();
  const [search, setSearch] = useState('');

  const query = useQuery({
    queryKey: ['professionals'],
    queryFn: () => api.listProfessionalsApiV1ProfessionalsGet(),
  });

  const professionals = useMemo(() => query.data ?? [], [query.data]);
  const selected = professionals.find((item) => item.id === value);

  const options = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return professionals.slice(0, SUGGESTIONS);
    return professionals
      .filter((professional) =>
        [
          professionalLabel(professional),
          professional.document_number,
          professionalDetail(professional),
        ]
          .join(' ')
          .toLowerCase()
          .includes(term),
      )
      .slice(0, SUGGESTIONS);
  }, [professionals, search]);

  if (selected) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2">
        <div>
          <p className="text-sm font-medium text-slate-700">{professionalLabel(selected)}</p>
          {professionalDetail(selected) && (
            <p className="text-xs text-slate-400">{professionalDetail(selected)}</p>
          )}
        </div>
        <ActionButton tone="neutral" onClick={() => onSelect('')} disabled={disabled}>
          Cambiar
        </ActionButton>
      </div>
    );
  }

  return (
    <div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={search}
          disabled={disabled}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={placeholder}
          className={`${inputClass} pl-10`}
        />
      </div>
      <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-slate-100">
        {query.isLoading && <p className="px-3 py-2 text-xs text-slate-400">Buscando...</p>}
        {!query.isLoading && options.length === 0 && (
          <p className="px-3 py-2 text-xs text-slate-400">
            Ningun profesional coincide con la busqueda.
          </p>
        )}
        {options.map((professional) => (
          <button
            key={professional.id}
            type="button"
            onClick={() => {
              onSelect(professional.id);
              setSearch('');
            }}
            className="flex w-full flex-col items-start px-3 py-2 text-left transition-colors hover:bg-slate-50"
          >
            <span className="text-sm text-slate-700">{professionalLabel(professional)}</span>
            {professionalDetail(professional) && (
              <span className="text-xs text-slate-400">{professionalDetail(professional)}</span>
            )}
          </button>
        ))}
        {!query.isLoading && emptyLabel && (
          <button
            type="button"
            onClick={() => onSelect('')}
            className="w-full border-t border-slate-100 px-3 py-2 text-left text-xs text-slate-400 hover:bg-slate-50"
          >
            {emptyLabel}
          </button>
        )}
      </div>
    </div>
  );
}
