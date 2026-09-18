import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPractices } from '@/api/endpoints/practices/practices';
import { getRegistry } from '@/api/endpoints/registry/registry';
import type {
  HealthPlanPracticeRead,
  HealthPlanPracticeUpdate,
  MedicalPracticeRead,
  PracticeChapter,
} from '@/api/model';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  PageHeader,
  Spinner,
  inputClass,
} from '@/components/ui';
import { CHAPTER_LABELS, money } from '@/components/practices/labels';
import { apiErrorMessage } from '@/utils/api-error';
import { ArrowLeft, Check, Pencil, Plus, Search, ShieldAlert, Trash2, X } from 'lucide-react';

type Conditions = {
  is_covered: boolean;
  /** Vacio: rige la carencia de la practica. */
  waiting_period_days: string;
  own_waiting_period: boolean;
  copayment_amount: string;
  requires_authorization: boolean;
  notes: string;
};

const defaultConditions: Conditions = {
  is_covered: true,
  waiting_period_days: '0',
  own_waiting_period: false,
  copayment_amount: '0',
  requires_authorization: false,
  notes: '',
};

function toUpdate(conditions: Conditions): HealthPlanPracticeUpdate {
  return {
    is_covered: conditions.is_covered,
    // Sin carencia propia se manda vacio y el plan hereda la de la practica.
    waiting_period_days: conditions.own_waiting_period
      ? Number(conditions.waiting_period_days || 0)
      : null,
    copayment_amount: Number(conditions.copayment_amount || 0).toFixed(2),
    requires_authorization: conditions.requires_authorization,
    notes: conditions.notes.trim() || null,
  };
}

function toConditions(entry: HealthPlanPracticeRead): Conditions {
  return {
    is_covered: entry.is_covered,
    waiting_period_days: String(entry.waiting_period_days ?? entry.practice_waiting_period_days),
    own_waiting_period: entry.waiting_period_days !== null,
    copayment_amount: entry.copayment_amount,
    requires_authorization: entry.requires_authorization,
    notes: entry.notes ?? '',
  };
}

const waitingLabel = (days: number) => {
  if (days === 0) return 'Sin carencia';
  if (days % 30 === 0) return `${days / 30} ${days === 30 ? 'mes' : 'meses'}`;
  return `${days} dias`;
};

/**
 * Cartilla de un plan: qué prácticas del nomenclador cubre y en qué condiciones — carencia,
 * copago y autorización. Estar en la lista es lo que hace que la práctica esté cubierta;
 * desactivarla deja constancia de que el plan la excluye.
 */
export default function PlanPracticesPage() {
  const { planId = '' } = useParams();
  const registry = getRegistry();
  const catalog = getPractices();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [chapter, setChapter] = useState<PracticeChapter | ''>('');
  const [onlyCovered, setOnlyCovered] = useState(false);
  const [editing, setEditing] = useState<HealthPlanPracticeRead | null>(null);
  const [conditions, setConditions] = useState<Conditions>(defaultConditions);
  const [addOpen, setAddOpen] = useState(false);
  const [addSearch, setAddSearch] = useState('');
  const [addChapter, setAddChapter] = useState<PracticeChapter | ''>('');
  const [selected, setSelected] = useState<string[]>([]);
  const [addConditions, setAddConditions] = useState<Conditions>(defaultConditions);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const planQuery = useQuery({
    queryKey: ['health-plan', planId],
    queryFn: () => registry.getHealthPlanApiV1HealthPlansHealthPlanIdGet(planId),
    enabled: planId !== '',
  });

  const payerQuery = useQuery({
    queryKey: ['payer', planQuery.data?.payer_id],
    queryFn: () => registry.getPayerApiV1PayersPayerIdGet(planQuery.data!.payer_id),
    enabled: Boolean(planQuery.data?.payer_id),
  });

  const cartillaQuery = useQuery({
    queryKey: ['plan-practices', planId, chapter, search, onlyCovered],
    queryFn: () =>
      registry.listHealthPlanPracticesApiV1HealthPlansHealthPlanIdPracticesGet(planId, {
        chapter: chapter || undefined,
        search: search.trim() || undefined,
        only_covered: onlyCovered,
      }),
    enabled: planId !== '',
  });

  // Todo el catálogo, para elegir qué sumar a la cartilla.
  const catalogQuery = useQuery({
    queryKey: ['practices', addChapter, addSearch],
    queryFn: () =>
      catalog.listPracticesApiV1PracticesGet({
        chapter: addChapter || undefined,
        search: addSearch.trim() || undefined,
        only_active: true,
      }),
    enabled: addOpen,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['plan-practices', planId] });

  const updateMutation = useMutation({
    mutationFn: ({ entryId, data }: { entryId: string; data: HealthPlanPracticeUpdate }) =>
      registry.updateHealthPlanPracticeApiV1HealthPlansHealthPlanIdPracticesPlanPracticeIdPut(
        planId,
        entryId,
        data,
      ),
    onSuccess: () => {
      invalidate();
      setEditing(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar la practica.')),
  });

  const deleteMutation = useMutation({
    mutationFn: (entryId: string) =>
      registry.unlinkHealthPlanPracticeApiV1HealthPlansHealthPlanIdPracticesPlanPracticeIdDelete(
        planId,
        entryId,
      ),
    onSuccess: invalidate,
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo quitar la practica.')),
  });

  const bulkMutation = useMutation({
    mutationFn: () =>
      registry.linkHealthPlanPracticesApiV1HealthPlansHealthPlanIdPracticesBulkPost(planId, {
        practice_ids: selected,
        ...toUpdate(addConditions),
      }),
    onSuccess: (result) => {
      invalidate();
      setSelected([]);
      setAddOpen(false);
      const skipped = result.skipped_practice_ids.length;
      setNotice(
        `${result.created.length} practicas agregadas a la cartilla` +
          (skipped > 0 ? `, ${skipped} ya estaban cargadas y no se modificaron` : ''),
      );
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudieron agregar las practicas.')),
  });

  const toggleCovered = (entry: HealthPlanPracticeRead) => {
    setError(null);
    updateMutation.mutate({
      entryId: entry.id,
      data: { ...toUpdate(toConditions(entry)), is_covered: !entry.is_covered },
    });
  };

  const openEdit = (entry: HealthPlanPracticeRead) => {
    setEditing(entry);
    setConditions(toConditions(entry));
    setError(null);
  };

  const submitEdit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!editing) return;
    setError(null);
    updateMutation.mutate({ entryId: editing.id, data: toUpdate(conditions) });
  };

  const openAdd = () => {
    setAddOpen(true);
    setAddSearch('');
    setAddChapter('');
    setSelected([]);
    setAddConditions(defaultConditions);
    setError(null);
    setNotice(null);
  };

  const toggleSelected = (practiceId: string) => {
    setSelected((current) =>
      current.includes(practiceId)
        ? current.filter((id) => id !== practiceId)
        : [...current, practiceId],
    );
  };

  const entries = cartillaQuery.data ?? [];
  const inCartilla = new Set(entries.map((entry) => entry.practice_id));
  const candidates = (catalogQuery.data ?? []).filter(
    (practice: MedicalPracticeRead) => !inCartilla.has(practice.id),
  );

  return (
    <div>
      <PageHeader
        title={`Cartilla de ${planQuery.data?.name ?? 'plan'}`}
        subtitle={
          payerQuery.data
            ? `${payerQuery.data.name} · practicas cubiertas y sus condiciones`
            : 'Practicas cubiertas y sus condiciones'
        }
        action={
          <div className="flex gap-2">
            <Link to="/coverages">
              <ActionButton tone="neutral">
                <ArrowLeft className="h-4 w-4" />
                Coberturas
              </ActionButton>
            </Link>
            <ActionButton tone="primary" onClick={openAdd}>
              <Plus className="h-4 w-4" />
              Agregar practicas
            </ActionButton>
          </div>
        }
      />

      {error && (
        <Card className="mb-4 border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm font-medium text-red-600">{error}</p>
        </Card>
      )}
      {notice && (
        <Card className="mb-4 border-teal-200 bg-teal-50 px-4 py-3">
          <p className="text-sm font-medium text-teal-700">{notice}</p>
        </Card>
      )}

      <Card className="mb-4 flex flex-col gap-3 p-4 md:flex-row md:items-center">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por codigo o nombre"
            className="w-full text-sm outline-none placeholder:text-slate-400"
          />
        </div>
        <select
          value={chapter}
          onChange={(event) => setChapter(event.target.value as PracticeChapter | '')}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
        >
          <option value="">Todos los capitulos</option>
          {Object.entries(CHAPTER_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={onlyCovered}
            onChange={(event) => setOnlyCovered(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Solo cubiertas
        </label>
      </Card>

      {cartillaQuery.isLoading && <Spinner />}
      {cartillaQuery.isError && <ErrorState message="No se pudo cargar la cartilla del plan." />}

      {cartillaQuery.data && (
        <Card className="overflow-hidden">
          {entries.length === 0 ? (
            <EmptyState message="El plan todavia no tiene practicas en su cartilla." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold">Practica</th>
                    <th className="px-4 py-3 text-left font-semibold">Capitulo</th>
                    <th className="px-4 py-3 text-center font-semibold">Cubierta</th>
                    <th className="px-4 py-3 text-left font-semibold">Carencia</th>
                    <th className="px-4 py-3 text-right font-semibold">Copago</th>
                    <th className="px-4 py-3 text-center font-semibold">Autorizacion</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className={entry.is_covered ? 'hover:bg-slate-50' : 'bg-slate-50/60'}
                    >
                      <td className="px-4 py-3">
                        <p
                          className={`font-semibold ${
                            entry.is_covered ? 'text-slate-700' : 'text-slate-400 line-through'
                          }`}
                        >
                          {entry.practice_name}
                        </p>
                        <p className="text-xs text-slate-400">{entry.practice_code}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{CHAPTER_LABELS[entry.chapter]}</td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => toggleCovered(entry)}
                          disabled={updateMutation.isPending}
                          title={entry.is_covered ? 'Desactivar practica' : 'Activar practica'}
                          className={`inline-flex h-7 w-7 items-center justify-center rounded-full transition-colors disabled:opacity-40 ${
                            entry.is_covered
                              ? 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100'
                              : 'bg-slate-200 text-slate-500 hover:bg-slate-300'
                          }`}
                        >
                          {entry.is_covered ? (
                            <Check className="h-4 w-4" />
                          ) : (
                            <X className="h-4 w-4" />
                          )}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {waitingLabel(entry.effective_waiting_period_days)}
                        <span className="block text-[11px] text-slate-400">
                          {entry.waiting_period_days === null
                            ? 'De la practica'
                            : 'Pactada en el plan'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-slate-600">
                        {Number(entry.copayment_amount) > 0
                          ? money(entry.copayment_amount)
                          : 'Sin copago'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {entry.requires_authorization ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
                            <ShieldAlert className="h-3.5 w-3.5" />
                            Requiere
                          </span>
                        ) : (
                          <span className="text-xs text-slate-400">No</span>
                        )}
                        {entry.practice_requires_authorization &&
                          !entry.requires_authorization && (
                            <p className="mt-1 text-[11px] text-slate-400">
                              El nomenclador la exige
                            </p>
                          )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => openEdit(entry)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Editar condiciones"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              setError(null);
                              if (
                                window.confirm(
                                  `Quitar "${entry.practice_name}" de la cartilla? Para dejar asentado que el plan no la cubre, desactivela en lugar de quitarla.`,
                                )
                              ) {
                                deleteMutation.mutate(entry.id);
                              }
                            }}
                            disabled={deleteMutation.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                            title="Quitar de la cartilla"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing ? `Condiciones de ${editing.practice_name}` : ''}
      >
        <form onSubmit={submitEdit} className="space-y-4">
          <ConditionsFields
            value={conditions}
            onChange={setConditions}
            practiceWaitingPeriod={editing?.practice_waiting_period_days}
          />
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setEditing(null)}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Agregar practicas a la cartilla"
        maxWidth="max-w-4xl"
      >
        <div className="space-y-5">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-xs text-slate-500">
            Las condiciones se aplican a todas las practicas seleccionadas. Las que ya estan en
            la cartilla no aparecen en la lista: sus condiciones se editan una por una.
          </p>

          <div className="flex flex-col gap-3 md:flex-row">
            <div className="flex flex-1 items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
              <Search className="h-4 w-4 text-slate-400" />
              <input
                value={addSearch}
                onChange={(event) => setAddSearch(event.target.value)}
                placeholder="Buscar en el nomenclador"
                className="w-full text-sm outline-none placeholder:text-slate-400"
              />
            </div>
            <select
              value={addChapter}
              onChange={(event) => setAddChapter(event.target.value as PracticeChapter | '')}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
            >
              <option value="">Todos los capitulos</option>
              {Object.entries(CHAPTER_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {catalogQuery.isLoading && <Spinner />}
          {catalogQuery.data && candidates.length === 0 && (
            <EmptyState message="No hay practicas para agregar con ese filtro." />
          )}
          {candidates.length > 0 && (
            <ul className="max-h-64 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200">
              {candidates.map((practice) => (
                <li key={practice.id}>
                  <label className="flex cursor-pointer items-center gap-3 px-4 py-2.5 hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={selected.includes(practice.id)}
                      onChange={() => toggleSelected(practice.id)}
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    <span className="flex-1">
                      <span className="block text-sm font-medium text-slate-700">
                        {practice.name}
                      </span>
                      <span className="block text-xs text-slate-400">
                        {practice.code} · {CHAPTER_LABELS[practice.chapter]}
                      </span>
                    </span>
                    {practice.requires_authorization && (
                      <span className="text-[11px] font-medium text-amber-600">
                        Requiere autorizacion
                      </span>
                    )}
                  </label>
                </li>
              ))}
            </ul>
          )}

          <ConditionsFields value={addConditions} onChange={setAddConditions} />
          <FormError message={error} />

          <div className="flex items-center justify-between pt-2">
            <p className="text-sm text-slate-500">{selected.length} practicas seleccionadas</p>
            <div className="flex gap-3">
              <ActionButton tone="neutral" onClick={() => setAddOpen(false)}>
                Cancelar
              </ActionButton>
              <ActionButton
                tone="primary"
                onClick={() => {
                  setError(null);
                  bulkMutation.mutate();
                }}
                disabled={selected.length === 0 || bulkMutation.isPending}
              >
                {bulkMutation.isPending ? 'Agregando...' : 'Agregar a la cartilla'}
              </ActionButton>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function ConditionsFields({
  value,
  onChange,
  practiceWaitingPeriod,
}: {
  value: Conditions;
  onChange: (conditions: Conditions) => void;
  /** Carencia de la practica, la que rige mientras el plan no pacte la suya. */
  practiceWaitingPeriod?: number;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field label="Carencia">
        <label className="mb-2 flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={!value.own_waiting_period}
            onChange={(event) =>
              onChange({ ...value, own_waiting_period: !event.target.checked })
            }
            className="h-4 w-4 rounded border-slate-300"
          />
          Usar la de la practica
          {practiceWaitingPeriod !== undefined && ` (${waitingLabel(practiceWaitingPeriod)})`}
        </label>
        <input
          type="number"
          min={0}
          max={3650}
          disabled={!value.own_waiting_period}
          value={value.waiting_period_days}
          onChange={(event) => onChange({ ...value, waiting_period_days: event.target.value })}
          className={`${inputClass} disabled:bg-slate-50 disabled:text-slate-400`}
        />
      </Field>
      <Field label="Copago">
        <input
          type="number"
          min={0}
          step="0.01"
          value={value.copayment_amount}
          onChange={(event) => onChange({ ...value, copayment_amount: event.target.value })}
          className={inputClass}
        />
      </Field>
      <div className="space-y-2 md:col-span-2">
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={value.is_covered}
            onChange={(event) => onChange({ ...value, is_covered: event.target.checked })}
            className="h-4 w-4 rounded border-slate-300"
          />
          Practica cubierta por el plan
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={value.requires_authorization}
            onChange={(event) =>
              onChange({ ...value, requires_authorization: event.target.checked })
            }
            className="h-4 w-4 rounded border-slate-300"
          />
          Requiere autorizacion del financiador
        </label>
      </div>
      <Field label="Observaciones">
        <input
          type="text"
          value={value.notes}
          onChange={(event) => onChange({ ...value, notes: event.target.value })}
          className={inputClass}
        />
      </Field>
    </div>
  );
}
