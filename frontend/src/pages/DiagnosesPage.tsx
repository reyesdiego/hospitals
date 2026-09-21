import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDiagnoses } from '@/api/endpoints/diagnoses/diagnoses';
import type { DiagnosisCodeCreate, DiagnosisCodeRead, DiagnosisLevel } from '@/api/model';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  PageHeader,
  Spinner,
  inputClass,
} from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { Pencil, Plus, Search, Trash2 } from 'lucide-react';

const LEVEL_LABELS: Record<DiagnosisLevel, string> = {
  CHAPTER: 'Capitulo',
  BLOCK: 'Grupo',
  CATEGORY: 'Categoria',
  SUBCATEGORY: 'Subcategoria',
};

const LEVEL_COLORS: Record<DiagnosisLevel, string> = {
  CHAPTER: 'bg-slate-100 text-slate-600',
  BLOCK: 'bg-slate-100 text-slate-600',
  CATEGORY: 'bg-teal-50 text-teal-700',
  SUBCATEGORY: 'bg-cyan-50 text-cyan-700',
};

/** El catalogo tiene mas de catorce mil codigos: se muestra una tanda por busqueda. */
const PAGE_SIZE = 100;

const emptyForm: DiagnosisCodeCreate = {
  code: '',
  description: '',
  level: 'SUBCATEGORY',
  parent_code: '',
  chapter_code: '',
  is_active: true,
  notes: '',
};

export default function DiagnosesPage() {
  const api = getDiagnoses();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [chapter, setChapter] = useState('');
  const [level, setLevel] = useState<'' | DiagnosisLevel>('');
  const [onlyActive, setOnlyActive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DiagnosisCodeRead | null>(null);
  const [form, setForm] = useState<DiagnosisCodeCreate>(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const chaptersQuery = useQuery({
    queryKey: ['diagnoses', 'chapters'],
    queryFn: () => api.listDiagnosesApiV1DiagnosesGet({ level: 'CHAPTER', limit: 50 }),
  });

  const codesQuery = useQuery({
    queryKey: ['diagnoses', search, chapter, level, onlyActive],
    queryFn: () =>
      api.listDiagnosesApiV1DiagnosesGet({
        search: search.trim() || undefined,
        chapter_code: chapter || undefined,
        level: level || undefined,
        only_active: onlyActive,
        limit: PAGE_SIZE,
      }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['diagnoses'] });

  const closeModal = () => {
    setModalOpen(false);
    setEditing(null);
    setForm(emptyForm);
    setError(null);
  };

  const saveMutation = useMutation({
    mutationFn: () => {
      const data = {
        ...form,
        code: form.code.trim().toUpperCase(),
        parent_code: form.parent_code?.trim() || null,
        chapter_code: form.chapter_code?.trim() || null,
        notes: form.notes?.trim() || null,
      };
      if (editing) {
        // El codigo es la identidad del diagnostico: se edita todo lo demas.
        return api.updateDiagnosisApiV1DiagnosesDiagnosisIdPut(editing.id, {
          description: data.description,
          level: data.level,
          parent_code: data.parent_code,
          chapter_code: data.chapter_code,
          is_active: data.is_active,
          notes: data.notes,
        });
      }
      return api.createDiagnosisApiV1DiagnosesPost(data);
    },
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar el diagnostico.')),
  });

  const deleteMutation = useMutation({
    mutationFn: (diagnosisId: string) =>
      api.deleteDiagnosisApiV1DiagnosesDiagnosisIdDelete(diagnosisId),
    onSuccess: () => {
      invalidate();
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo eliminar el diagnostico.')),
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ ...emptyForm, chapter_code: chapter });
    setError(null);
    setModalOpen(true);
  };

  const openEdit = (entry: DiagnosisCodeRead) => {
    setEditing(entry);
    setForm({
      code: entry.code,
      description: entry.description,
      level: entry.level,
      parent_code: entry.parent_code ?? '',
      chapter_code: entry.chapter_code ?? '',
      is_active: entry.is_active,
      notes: entry.notes ?? '',
    });
    setError(null);
    setModalOpen(true);
  };

  const remove = (entry: DiagnosisCodeRead) => {
    if (
      !window.confirm(
        `Eliminar el diagnostico ${entry.code}? Si ya se uso, desactivelo en lugar de borrarlo.`,
      )
    ) {
      return;
    }
    deleteMutation.mutate(entry.id);
  };

  const chapters = chaptersQuery.data ?? [];
  const codes = codesQuery.data ?? [];

  return (
    <div>
      <PageHeader
        title="Diagnosticos CIE-10"
        subtitle="Clasificacion internacional de enfermedades: capitulos, grupos, categorias y subcategorias"
        action={
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
          >
            <Plus className="h-4 w-4" />
            Nuevo diagnostico
          </button>
        }
      />

      <Card className="mb-4 p-4">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px_180px_auto]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Codigo o texto del diagnostico"
              className={`${inputClass} pl-10`}
            />
          </div>
          <select
            value={chapter}
            onChange={(event) => setChapter(event.target.value)}
            className={inputClass}
          >
            <option value="">Todos los capitulos</option>
            {chapters.map((item) => (
              <option key={item.id} value={item.code}>
                {item.code} - {item.description}
              </option>
            ))}
          </select>
          <select
            value={level}
            onChange={(event) => setLevel(event.target.value as '' | DiagnosisLevel)}
            className={inputClass}
          >
            <option value="">Todos los niveles</option>
            {Object.entries(LEVEL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={onlyActive}
              onChange={(event) => setOnlyActive(event.target.checked)}
              className="h-4 w-4 accent-teal-600"
            />
            Solo vigentes
          </label>
        </div>
      </Card>

      <FormError message={error} />

      {codesQuery.isLoading && <Spinner />}
      {codesQuery.isError && <ErrorState message="No se pudo cargar el catalogo CIE-10." />}

      {codesQuery.data && (
        <Card className="overflow-hidden">
          {codes.length === 0 ? (
            <EmptyState message="Ningun diagnostico coincide con la busqueda." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-5 py-3 text-left font-semibold">Codigo</th>
                    <th className="px-5 py-3 text-left font-semibold">Diagnostico</th>
                    <th className="px-5 py-3 text-left font-semibold">Nivel</th>
                    <th className="px-5 py-3 text-left font-semibold">Depende de</th>
                    <th className="px-5 py-3 text-right font-semibold">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {codes.map((entry) => (
                    <tr
                      key={entry.id}
                      className={`hover:bg-slate-50 ${entry.is_active ? '' : 'bg-slate-50/60'}`}
                    >
                      <td className="px-5 py-3">
                        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-bold text-slate-700">
                          {entry.code}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <p
                          className={`font-medium ${
                            entry.is_active ? 'text-slate-700' : 'text-slate-400 line-through'
                          }`}
                        >
                          {entry.description}
                        </p>
                        {entry.notes && <p className="text-xs text-slate-400">{entry.notes}</p>}
                      </td>
                      <td className="px-5 py-3">
                        <Badge
                          status={LEVEL_LABELS[entry.level]}
                          color={LEVEL_COLORS[entry.level]}
                        />
                      </td>
                      <td className="px-5 py-3 text-xs text-slate-500">
                        {entry.parent_code ?? '-'}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => openEdit(entry)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Editar diagnostico"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => remove(entry)}
                            disabled={deleteMutation.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                            title="Eliminar diagnostico"
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
          {codes.length === PAGE_SIZE && (
            <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-400">
              Se muestran los primeros {PAGE_SIZE} codigos: afine la busqueda para ver el resto.
            </p>
          )}
        </Card>
      )}

      <Modal
        open={modalOpen}
        onClose={closeModal}
        title={editing ? `Diagnostico ${editing.code}` : 'Nuevo diagnostico'}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            saveMutation.mutate();
          }}
          className="space-y-4"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Codigo">
              <input
                type="text"
                required
                disabled={editing !== null}
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
                placeholder="J159"
                className={`${inputClass} disabled:bg-slate-50 disabled:text-slate-400`}
              />
            </Field>
            <Field label="Nivel">
              <select
                value={form.level}
                onChange={(event) =>
                  setForm({ ...form, level: event.target.value as DiagnosisLevel })
                }
                className={inputClass}
              >
                {Object.entries(LEVEL_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Diagnostico">
            <input
              type="text"
              required
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              className={inputClass}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Depende de (codigo padre)">
              <input
                type="text"
                value={form.parent_code ?? ''}
                onChange={(event) =>
                  setForm({ ...form, parent_code: event.target.value.toUpperCase() })
                }
                placeholder="J15"
                className={inputClass}
              />
            </Field>
            <Field label="Capitulo">
              <select
                value={form.chapter_code ?? ''}
                onChange={(event) => setForm({ ...form, chapter_code: event.target.value })}
                className={inputClass}
              >
                <option value="">Sin capitulo</option>
                {chapters.map((item) => (
                  <option key={item.id} value={item.code}>
                    {item.code} - {item.description}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Notas">
            <input
              type="text"
              value={form.notes ?? ''}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              className={inputClass}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.is_active ?? true}
              onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
              className="h-4 w-4 accent-teal-600"
            />
            Vigente
          </label>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={closeModal}>
              Cancelar
            </ActionButton>
            <button
              type="submit"
              disabled={saveMutation.isPending}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {saveMutation.isPending ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
