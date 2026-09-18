import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPractices } from '@/api/endpoints/practices/practices';
import {
  Nomenclador,
  PracticeChapter,
  PracticeSetting,
  PracticeType,
  type MedicalPracticeCreate,
  type MedicalPracticeRead,
} from '@/api/model';
import { PageHeader, Card, Spinner, ErrorState, EmptyState, Field, FormError, inputClass } from '@/components/ui';
import Modal from '@/components/Modal';
import PracticeTariffsModal from '@/components/practices/PracticeTariffsModal';
import {
  CHAPTER_LABELS,
  NOMENCLADOR_LABELS,
  NOMENCLADOR_SHORT,
  PRACTICE_TYPE_LABELS,
  SETTING_LABELS,
  UNIT_FIELDS,
  UNIT_LABELS,
  period,
  units,
} from '@/components/practices/labels';
import { apiErrorMessage } from '@/utils/api-error';
import { CircleDollarSign, ClipboardList, Pencil, Plus, Trash2 } from 'lucide-react';

type PracticeForm = {
  nomenclador: Nomenclador;
  code: string;
  name: string;
  description: string;
  chapter: PracticeChapter;
  practice_type: PracticeType;
  setting: PracticeSetting;
  galeno_units: string;
  expense_units: string;
  anesthesia_units: string;
  biochemical_units: string;
  radiology_units: string;
  requires_authorization: boolean;
  requires_consent: boolean;
  is_active: boolean;
  valid_from: string;
  valid_until: string;
  notes: string;
};

const emptyForm: PracticeForm = {
  nomenclador: 'NACIONAL',
  code: '',
  name: '',
  description: '',
  chapter: 'CONSULTAS',
  practice_type: 'CONSULTA',
  setting: 'AMBOS',
  galeno_units: '0',
  expense_units: '0',
  anesthesia_units: '0',
  biochemical_units: '0',
  radiology_units: '0',
  requires_authorization: false,
  requires_consent: false,
  is_active: true,
  valid_from: '',
  valid_until: '',
  notes: '',
};

function toPayload(form: PracticeForm): MedicalPracticeCreate {
  const unit = (value: string) => (value.trim() === '' ? '0' : value.trim());
  return {
    nomenclador: form.nomenclador,
    code: form.code.trim(),
    name: form.name.trim(),
    description: form.description.trim() || null,
    chapter: form.chapter,
    practice_type: form.practice_type,
    setting: form.setting,
    galeno_units: unit(form.galeno_units),
    expense_units: unit(form.expense_units),
    anesthesia_units: unit(form.anesthesia_units),
    biochemical_units: unit(form.biochemical_units),
    radiology_units: unit(form.radiology_units),
    requires_authorization: form.requires_authorization,
    requires_consent: form.requires_consent,
    is_active: form.is_active,
    valid_from: form.valid_from || null,
    valid_until: form.valid_until || null,
    notes: form.notes.trim() || null,
  };
}

function toForm(practice: MedicalPracticeRead): PracticeForm {
  return {
    nomenclador: practice.nomenclador,
    code: practice.code,
    name: practice.name,
    description: practice.description ?? '',
    chapter: practice.chapter,
    practice_type: practice.practice_type,
    setting: practice.setting,
    galeno_units: practice.galeno_units,
    expense_units: practice.expense_units,
    anesthesia_units: practice.anesthesia_units,
    biochemical_units: practice.biochemical_units,
    radiology_units: practice.radiology_units,
    requires_authorization: practice.requires_authorization,
    requires_consent: practice.requires_consent,
    is_active: practice.is_active,
    valid_from: practice.valid_from ?? '',
    valid_until: practice.valid_until ?? '',
    notes: practice.notes ?? '',
  };
}

/** Unidades con valor, para no mostrar los ceros de los capitulos que no las usan. */
function informedUnits(practice: MedicalPracticeRead) {
  return UNIT_FIELDS.filter((field) => Number(practice[field]) > 0).map((field) => ({
    label: UNIT_LABELS[field],
    value: units(practice[field]),
  }));
}

export default function MedicalPracticesPage() {
  const api = getPractices();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [nomenclador, setNomenclador] = useState<Nomenclador | ''>('');
  const [chapter, setChapter] = useState<PracticeChapter | ''>('');
  const [onlyActive, setOnlyActive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MedicalPracticeRead | null>(null);
  const [form, setForm] = useState<PracticeForm>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [tariffsFor, setTariffsFor] = useState<MedicalPracticeRead | null>(null);

  const filters = {
    search: search.trim() || undefined,
    nomenclador: nomenclador || undefined,
    chapter: chapter || undefined,
    only_active: onlyActive || undefined,
  };

  const practicesQuery = useQuery({
    queryKey: ['practices', filters],
    queryFn: () => api.listPracticesApiV1PracticesGet(filters),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['practices'] });

  const createMutation = useMutation({
    mutationFn: (data: MedicalPracticeCreate) => api.createPracticeApiV1PracticesPost(data),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (error) => setFormError(apiErrorMessage(error, 'No se pudo guardar la practica.')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ practiceId, data }: { practiceId: string; data: MedicalPracticeCreate }) =>
      api.updatePracticeApiV1PracticesPracticeIdPut(practiceId, data),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (error) => setFormError(apiErrorMessage(error, 'No se pudo guardar la practica.')),
  });

  const deleteMutation = useMutation({
    mutationFn: (practiceId: string) => api.deletePracticeApiV1PracticesPracticeIdDelete(practiceId),
    onSuccess: () => {
      setListError(null);
      invalidate();
    },
    onError: (error) => setListError(apiErrorMessage(error, 'No se pudo eliminar la practica.')),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (practice: MedicalPracticeRead) => {
    setEditing(practice);
    setForm(toForm(practice));
    setFormError(null);
    setModalOpen(true);
  };

  function closeModal() {
    setModalOpen(false);
    setEditing(null);
    setForm(emptyForm);
    setFormError(null);
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);
    const data = toPayload(form);
    if (editing) {
      updateMutation.mutate({ practiceId: editing.id, data });
      return;
    }
    createMutation.mutate(data);
  };

  const handleDelete = (practice: MedicalPracticeRead) => {
    if (!window.confirm(`Eliminar la practica "${practice.code} - ${practice.name}" y sus valores?`))
      return;
    deleteMutation.mutate(practice.id);
  };

  const practices = practicesQuery.data ?? [];
  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div>
      <PageHeader
        title="Practicas medicas"
        subtitle="Catalogo del nomenclador y valores acordados con cada financiador"
        action={
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
          >
            <Plus className="h-4 w-4" />
            Nueva practica
          </button>
        }
      />

      <Card className="mb-4 p-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Buscar por codigo o nombre">
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="42.01.01 o consulta"
              className={inputClass}
            />
          </Field>
          <Field label="Nomenclador">
            <select
              value={nomenclador}
              onChange={(event) => setNomenclador(event.target.value as Nomenclador | '')}
              className={inputClass}
            >
              <option value="">Todos</option>
              {Object.values(Nomenclador).map((value) => (
                <option key={value} value={value}>
                  {NOMENCLADOR_LABELS[value]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Capitulo">
            <select
              value={chapter}
              onChange={(event) => setChapter(event.target.value as PracticeChapter | '')}
              className={inputClass}
            >
              <option value="">Todos</option>
              {Object.values(PracticeChapter).map((value) => (
                <option key={value} value={value}>
                  {CHAPTER_LABELS[value]}
                </option>
              ))}
            </select>
          </Field>
          <label className="flex items-end gap-2 pb-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={onlyActive}
              onChange={(event) => setOnlyActive(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Solo practicas vigentes
          </label>
        </div>
      </Card>

      {practicesQuery.isLoading && <Spinner />}
      {practicesQuery.isError && (
        <ErrorState message="No se pudo cargar el catalogo de practicas." />
      )}

      {listError && (
        <Card className="mb-4 border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm font-medium text-red-600">{listError}</p>
        </Card>
      )}

      {practicesQuery.data && (
        <Card className="overflow-hidden">
          {practices.length === 0 ? (
            <EmptyState message="No hay practicas para los filtros aplicados." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Practica
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Nomenclador
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Unidades
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Requisitos
                    </th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-slate-500">
                      Acciones
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {practices.map((practice) => (
                    <tr key={practice.id} className="hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <div className="flex items-start gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-teal-50">
                            <ClipboardList className="h-5 w-5 text-teal-600" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-slate-800">
                              {practice.code} - {practice.name}
                            </p>
                            <p className="text-xs text-slate-400">
                              {CHAPTER_LABELS[practice.chapter]} ·{' '}
                              {PRACTICE_TYPE_LABELS[practice.practice_type]} ·{' '}
                              {SETTING_LABELS[practice.setting]}
                            </p>
                            <p className="text-xs text-slate-400">
                              {period(practice.valid_from, practice.valid_until)}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
                          {NOMENCLADOR_SHORT[practice.nomenclador]}
                        </span>
                        {!practice.is_active && (
                          <p className="mt-1 text-xs font-semibold text-red-500">Baja</p>
                        )}
                      </td>
                      <td className="px-5 py-4">
                        {informedUnits(practice).length === 0 ? (
                          <span className="text-xs text-slate-400">Sin unidades</span>
                        ) : (
                          <ul className="space-y-0.5">
                            {informedUnits(practice).map((unit) => (
                              <li key={unit.label} className="text-xs text-slate-600">
                                <span className="font-semibold text-slate-700">{unit.value}</span>{' '}
                                {unit.label}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-col gap-1">
                          {practice.requires_authorization && (
                            <span className="w-fit rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700">
                              Autorizacion previa
                            </span>
                          )}
                          {practice.requires_consent && (
                            <span className="w-fit rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                              Consentimiento
                            </span>
                          )}
                          {!practice.requires_authorization && !practice.requires_consent && (
                            <span className="text-xs text-slate-400">Sin requisitos</span>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => setTariffsFor(practice)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-emerald-50 hover:text-emerald-700"
                            title="Valores por financiador"
                          >
                            <CircleDollarSign className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => openEdit(practice)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Editar practica"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(practice)}
                            disabled={deleteMutation.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                            title="Eliminar practica"
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
        open={modalOpen}
        onClose={closeModal}
        title={editing ? 'Editar practica' : 'Nueva practica'}
        maxWidth="max-w-3xl"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nomenclador">
              <select
                value={form.nomenclador}
                onChange={(event) =>
                  setForm({ ...form, nomenclador: event.target.value as Nomenclador })
                }
                className={inputClass}
              >
                {Object.values(Nomenclador).map((value) => (
                  <option key={value} value={value}>
                    {NOMENCLADOR_LABELS[value]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Codigo">
              <input
                type="text"
                required
                maxLength={20}
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value })}
                placeholder="42.01.01"
                className={inputClass}
              />
            </Field>
          </div>

          <Field label="Nombre de la practica">
            <input
              type="text"
              required
              maxLength={250}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              className={inputClass}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Capitulo">
              <select
                value={form.chapter}
                onChange={(event) =>
                  setForm({ ...form, chapter: event.target.value as PracticeChapter })
                }
                className={inputClass}
              >
                {Object.values(PracticeChapter).map((value) => (
                  <option key={value} value={value}>
                    {CHAPTER_LABELS[value]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tipo">
              <select
                value={form.practice_type}
                onChange={(event) =>
                  setForm({ ...form, practice_type: event.target.value as PracticeType })
                }
                className={inputClass}
              >
                {Object.values(PracticeType).map((value) => (
                  <option key={value} value={value}>
                    {PRACTICE_TYPE_LABELS[value]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Ambito">
              <select
                value={form.setting}
                onChange={(event) =>
                  setForm({ ...form, setting: event.target.value as PracticeSetting })
                }
                className={inputClass}
              >
                {Object.values(PracticeSetting).map((value) => (
                  <option key={value} value={value}>
                    {SETTING_LABELS[value]}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div>
            <p className="mb-2 text-sm font-semibold text-slate-700">Unidades del nomenclador</p>
            <div className="grid gap-4 sm:grid-cols-3">
              {UNIT_FIELDS.map((field) => (
                <Field key={field} label={UNIT_LABELS[field]}>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={form[field]}
                    onChange={(event) => setForm({ ...form, [field]: event.target.value })}
                    className={inputClass}
                  />
                </Field>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Vigente desde">
              <input
                type="date"
                value={form.valid_from}
                onChange={(event) => setForm({ ...form, valid_from: event.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label="Vigente hasta">
              <input
                type="date"
                value={form.valid_until}
                onChange={(event) => setForm({ ...form, valid_until: event.target.value })}
                className={inputClass}
              />
            </Field>
          </div>

          <Field label="Descripcion">
            <textarea
              rows={2}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              className={inputClass}
            />
          </Field>

          <Field label="Observaciones">
            <input
              type="text"
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              className={inputClass}
            />
          </Field>

          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={form.requires_authorization}
                onChange={(event) =>
                  setForm({ ...form, requires_authorization: event.target.checked })
                }
                className="h-4 w-4 rounded border-slate-300"
              />
              Requiere autorizacion previa
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={form.requires_consent}
                onChange={(event) => setForm({ ...form, requires_consent: event.target.checked })}
                className="h-4 w-4 rounded border-slate-300"
              />
              Requiere consentimiento informado
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                className="h-4 w-4 rounded border-slate-300"
              />
              Vigente
            </label>
          </div>

          <FormError message={formError} />

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={closeModal}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {isSaving ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </Modal>

      <PracticeTariffsModal
        practice={tariffsFor}
        open={tariffsFor !== null}
        onClose={() => setTariffsFor(null)}
      />
    </div>
  );
}
