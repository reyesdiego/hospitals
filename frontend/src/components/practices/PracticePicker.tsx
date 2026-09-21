import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPractices } from '@/api/endpoints/practices/practices';
import type { MedicalPracticeRead } from '@/api/model';
import { inputClass } from '@/components/ui';
import { Search } from 'lucide-react';

/** Cuantas practicas se ofrecen por busqueda: el nomenclador no entra en un dropdown. */
const SUGGESTIONS = 12;

/** Buscador del nomenclador: se escribe codigo o texto y se elige de las coincidencias,
 * igual que el buscador de diagnosticos CIE-10. */
export default function PracticePicker({
  onSelect,
  placeholder = 'Buscar practica por codigo o nombre',
  disabled = false,
}: {
  onSelect: (practice: MedicalPracticeRead) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const api = getPractices();
  const [search, setSearch] = useState('');

  const query = useQuery({
    queryKey: ['practices', 'picker', search],
    queryFn: () =>
      api.listPracticesApiV1PracticesGet({ search: search.trim(), only_active: true }),
    enabled: search.trim().length >= 2,
  });

  const options = (query.data ?? []).slice(0, SUGGESTIONS);

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
      {search.trim().length >= 2 && (
        <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-slate-100">
          {query.isLoading && <p className="px-3 py-2 text-xs text-slate-400">Buscando...</p>}
          {!query.isLoading && options.length === 0 && (
            <p className="px-3 py-2 text-xs text-slate-400">
              Ninguna practica coincide con la busqueda.
            </p>
          )}
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => {
                onSelect(option);
                setSearch('');
              }}
              className="flex w-full items-start gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-slate-50"
            >
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">
                {option.code}
              </span>
              <span className="text-slate-600">
                {option.name}
                {option.is_nursing_task && (
                  <span className="ml-1 text-xs text-teal-600">(enfermeria)</span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
