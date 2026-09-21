import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDiagnoses } from '@/api/endpoints/diagnoses/diagnoses';
import type { DiagnosisCodeRead } from '@/api/model';
import { Badge, Spinner } from '@/components/ui';
import {
  DIAGNOSIS_LEVEL_COLORS,
  DIAGNOSIS_LEVEL_LABELS,
} from '@/config/diagnosisLabels';
import { ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from 'lucide-react';

/** Una rama puede tener muchas subcategorias; mas que esto se busca, no se navega. */
const BRANCH_LIMIT = 500;

export type TreeActions = {
  onEdit: (entry: DiagnosisCodeRead) => void;
  onRemove: (entry: DiagnosisCodeRead) => void;
  /** Alta de un codigo colgando del que se esta mirando. */
  onAddChild: (parent: DiagnosisCodeRead) => void;
  canManage: boolean;
  onlyActive: boolean;
};

/**
 * El catalogo se lee como lo que es: un arbol. Cada rama se pide cuando se abre, porque
 * son mas de catorce mil codigos y bajarlos todos para mostrar veintiuno no tiene sentido.
 */
export function DiagnosisRow({
  entry,
  depth,
  actions,
}: {
  entry: DiagnosisCodeRead;
  depth: number;
  actions: TreeActions;
}) {
  const api = getDiagnoses();
  const [open, setOpen] = useState(false);
  const hasChildren = (entry.child_count ?? 0) > 0;

  const childrenQuery = useQuery({
    queryKey: ['diagnoses', 'children', entry.code, actions.onlyActive],
    queryFn: () =>
      api.listDiagnosesApiV1DiagnosesGet({
        parent_code: entry.code,
        only_active: actions.onlyActive,
        limit: BRANCH_LIMIT,
      }),
    enabled: open && hasChildren,
  });

  const children = childrenQuery.data ?? [];

  return (
    <>
      <div
        className={`flex items-center gap-3 border-b border-slate-50 px-3 py-2 hover:bg-slate-50 ${
          entry.is_active ? '' : 'bg-slate-50/60'
        }`}
        style={{ paddingLeft: `${12 + depth * 22}px` }}
      >
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          disabled={!hasChildren}
          className="rounded p-0.5 text-slate-400 transition-colors hover:text-slate-700 disabled:opacity-0"
          title={open ? 'Contraer' : 'Desplegar'}
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        <span className="w-24 shrink-0 rounded-md bg-slate-100 px-2 py-1 text-xs font-bold text-slate-700">
          {entry.code}
        </span>

        <span className="min-w-0 flex-1">
          <span
            className={`block truncate text-sm ${
              entry.is_active ? 'text-slate-700' : 'text-slate-400 line-through'
            }`}
            title={entry.description}
          >
            {entry.description}
          </span>
          {entry.notes && <span className="block truncate text-xs text-slate-400">{entry.notes}</span>}
        </span>

        {hasChildren && (
          <span className="shrink-0 text-xs text-slate-400">{entry.child_count}</span>
        )}
        <Badge status={DIAGNOSIS_LEVEL_LABELS[entry.level]}
          color={DIAGNOSIS_LEVEL_COLORS[entry.level]} />

        {actions.canManage && (
          <span className="flex shrink-0 gap-1">
            <button
              type="button"
              onClick={() => actions.onAddChild(entry)}
              className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
              title="Agregar un codigo dentro de este"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => actions.onEdit(entry)}
              className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
              title="Editar diagnostico"
            >
              <Pencil className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => actions.onRemove(entry)}
              className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600"
              title="Eliminar diagnostico"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </span>
        )}
      </div>

      {open && childrenQuery.isLoading && (
        <div style={{ paddingLeft: `${40 + depth * 22}px` }} className="py-2">
          <Spinner />
        </div>
      )}
      {open &&
        children.map((child) => (
          <DiagnosisRow key={child.id} entry={child} depth={depth + 1} actions={actions} />
        ))}
      {open && childrenQuery.isSuccess && children.length === 0 && (
        <p
          style={{ paddingLeft: `${40 + depth * 22}px` }}
          className="border-b border-slate-50 py-2 text-xs text-slate-400"
        >
          Sin codigos vigentes en esta rama.
        </p>
      )}
    </>
  );
}

export default DiagnosisRow;
