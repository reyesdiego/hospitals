import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDiagnoses } from '@/api/endpoints/diagnoses/diagnoses';
import type { DiagnosisCodeRead } from '@/api/model';
import { inputClass } from '@/components/ui';
import { Search } from 'lucide-react';

/** Cuantos codigos se ofrecen por busqueda: el catalogo tiene mas de catorce mil. */
const SUGGESTIONS = 12;

/** Buscador del catalogo CIE-10 que solo ofrece codigos vigentes y codificables:
 * capitulos y grupos ordenan la clasificacion, no se le asientan a un paciente. */
export default function DiagnosisPicker({
  onSelect,
  placeholder = 'Buscar diagnostico por codigo o texto',
  disabled = false,
}: {
  onSelect: (code: DiagnosisCodeRead) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const api = getDiagnoses();
  const [search, setSearch] = useState('');

  const query = useQuery({
    queryKey: ['diagnoses', 'picker', search],
    queryFn: () =>
      api.listDiagnosesApiV1DiagnosesGet({
        search: search.trim(),
        only_active: true,
        only_codifiable: true,
        limit: SUGGESTIONS,
      }),
    enabled: search.trim().length >= 2,
  });

  const options = query.data ?? [];

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
              Ningun diagnostico coincide con la busqueda.
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
              <span className="text-slate-600">{option.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
