import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getRegistry } from '@/api/endpoints/registry/registry';
import type {
  CoverageStatus,
  PatientCoverageCreate,
  PatientCoverageRead,
  PatientRead,
} from '@/api/model';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Badge,
  EmptyState,
  Field,
  FormError,
  Spinner,
  inputClass,
} from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { Pencil, Plus, Trash2 } from 'lucide-react';

type CoverageForm = {
  payer_id: string;
  health_plan_id: string;
  payer_name: string;
  member_number: string;
  authorization_required: boolean;
  valid_from: string;
  valid_until: string;
  status: CoverageStatus;
};

const emptyForm: CoverageForm = {
  payer_id: '',
  health_plan_id: '',
  payer_name: '',
  member_number: '',
  authorization_required: false,
  valid_from: '',
  valid_until: '',
  status: 'ACTIVE',
};

const STATUS_LABELS: Record<CoverageStatus, { label: string; color: string }> = {
  ACTIVE: { label: 'Activa', color: 'bg-emerald-50 text-emerald-700' },
  INACTIVE: { label: 'Inactiva', color: 'bg-slate-100 text-slate-600' },
  EXPIRED: { label: 'Vencida', color: 'bg-amber-50 text-amber-700' },
};

/** A coverage with a payer from the catalog takes its names from there; one loaded from the
 * card the patient brings travels as free text in ``payer_name``. */
function toPayload(form: CoverageForm): PatientCoverageCreate {
  return {
    payer_id: form.payer_id || null,
    health_plan_id: form.health_plan_id || null,
    payer_name: form.payer_id ? null : form.payer_name.trim() || null,
    plan_name: null,
    member_number: form.member_number.trim() || null,
    authorization_required: form.authorization_required,
    valid_from: form.valid_from || null,
    valid_until: form.valid_until || null,
    status: form.status,
  };
}

function toForm(coverage: PatientCoverageRead): CoverageForm {
  return {
    payer_id: coverage.payer_id ?? '',
    health_plan_id: coverage.health_plan_id ?? '',
    payer_name: coverage.payer_name,
    member_number: coverage.member_number ?? '',
    authorization_required: coverage.authorization_required,
    valid_from: coverage.valid_from ?? '',
    valid_until: coverage.valid_until ?? '',
    status: coverage.status,
  };
}

export default function PatientCoveragesModal({
  patient,
  open,
  onClose,
}: {
  patient: PatientRead | null;
  open: boolean;
  onClose: () => void;
}) {
  const api = getRegistry();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CoverageForm>(emptyForm);
  const [editing, setEditing] = useState<PatientCoverageRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  const patientId = patient?.id ?? '';

  const coveragesQuery = useQuery({
    queryKey: ['patient-coverages', patientId],
    queryFn: () => api.listPatientCoveragesApiV1PatientsPatientIdCoveragesGet(patientId),
    enabled: open && patientId !== '',
  });

  const payersQuery = useQuery({
    queryKey: ['payers'],
    queryFn: () => api.listPayersApiV1PayersGet(),
    enabled: open,
  });

  const plansQuery = useQuery({
    queryKey: ['health-plans', form.payer_id],
    queryFn: () => api.listPayerHealthPlansApiV1PayersPayerIdHealthPlansGet(form.payer_id),
    enabled: open && form.payer_id !== '',
  });

  const reset = () => {
    setForm(emptyForm);
    setEditing(null);
    setError(null);
  };

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['patient-coverages', patientId] });

  const createMutation = useMutation({
    mutationFn: (data: PatientCoverageCreate) =>
      api.createPatientCoverageApiV1PatientsPatientIdCoveragesPost(patientId, data),
    onSuccess: () => {
      invalidate();
      reset();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar la cobertura.')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ coverageId, data }: { coverageId: string; data: PatientCoverageCreate }) =>
      api.updateCoverageApiV1CoveragesCoverageIdPut(coverageId, data),
    onSuccess: () => {
      invalidate();
      reset();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar la cobertura.')),
  });

  const deleteMutation = useMutation({
    mutationFn: (coverageId: string) =>
      api.deleteCoverageApiV1CoveragesCoverageIdDelete(coverageId),
    onSuccess: invalidate,
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo eliminar la cobertura.')),
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const data = toPayload(form);
    if (editing) {
      updateMutation.mutate({ coverageId: editing.id, data });
      return;
    }
    createMutation.mutate(data);
  };

  const closeModal = () => {
    reset();
    onClose();
  };

  const coverages = coveragesQuery.data ?? [];
  const payers = payersQuery.data ?? [];
  const plans = plansQuery.data ?? [];
  const isSaving = createMutation.isPending || updateMutation.isPending;

  if (!patient) return null;

  return (
    <Modal
      open={open}
      onClose={closeModal}
      title={`Coberturas de ${patient.first_name} ${patient.last_name}`}
      maxWidth="max-w-3xl"
    >
      <div className="space-y-6">
        {coveragesQuery.isLoading && <Spinner />}
        {!coveragesQuery.isLoading && coverages.length === 0 && (
          <EmptyState message="El paciente no tiene coberturas cargadas." />
        )}

        {coverages.length > 0 && (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
            {coverages.map((coverage) => (
              <li key={coverage.id} className="flex items-start justify-between gap-3 px-4 py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-700">
                      {coverage.payer_name}
                      {coverage.plan_name ? ` · ${coverage.plan_name}` : ''}
                    </p>
                    <Badge
                      status={STATUS_LABELS[coverage.status].label}
                      color={STATUS_LABELS[coverage.status].color}
                    />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {coverage.member_number ? `Afiliado ${coverage.member_number}` : 'Sin afiliado'}
                    {coverage.valid_from ? ` · desde ${coverage.valid_from}` : ''}
                    {coverage.valid_until ? ` hasta ${coverage.valid_until}` : ''}
                    {coverage.authorization_required ? ' · requiere autorizacion' : ''}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setEditing(coverage);
                      setForm(toForm(coverage));
                      setError(null);
                    }}
                    className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                    title="Editar cobertura"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => {
                      setError(null);
                      if (window.confirm('Eliminar esta cobertura?')) {
                        deleteMutation.mutate(coverage.id);
                      }
                    }}
                    disabled={deleteMutation.isPending}
                    className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                    title="Eliminar cobertura"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 border-t border-slate-100 pt-5">
          <p className="text-sm font-semibold text-slate-700">
            {editing ? 'Editar cobertura' : 'Nueva cobertura'}
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Financiador">
              <select
                value={form.payer_id}
                onChange={(event) =>
                  setForm({ ...form, payer_id: event.target.value, health_plan_id: '' })
                }
                className={inputClass}
              >
                <option value="">Sin catalogo (cargar a mano)</option>
                {payers.map((payer) => (
                  <option key={payer.id} value={payer.id}>
                    {payer.name}
                  </option>
                ))}
              </select>
            </Field>

            {form.payer_id ? (
              <Field label="Plan">
                <select
                  value={form.health_plan_id}
                  onChange={(event) => setForm({ ...form, health_plan_id: event.target.value })}
                  className={inputClass}
                >
                  <option value="">Sin plan</option>
                  {plans.map((plan) => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name}
                    </option>
                  ))}
                </select>
              </Field>
            ) : (
              <Field label="Nombre del financiador">
                <input
                  type="text"
                  required
                  value={form.payer_name}
                  onChange={(event) => setForm({ ...form, payer_name: event.target.value })}
                  className={inputClass}
                />
              </Field>
            )}

            <Field label="Numero de afiliado">
              <input
                type="text"
                value={form.member_number}
                onChange={(event) => setForm({ ...form, member_number: event.target.value })}
                className={inputClass}
              />
            </Field>

            <Field label="Estado">
              <select
                value={form.status}
                onChange={(event) =>
                  setForm({ ...form, status: event.target.value as CoverageStatus })
                }
                className={inputClass}
              >
                {(Object.keys(STATUS_LABELS) as CoverageStatus[]).map((status) => (
                  <option key={status} value={status}>
                    {STATUS_LABELS[status].label}
                  </option>
                ))}
              </select>
            </Field>

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

          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.authorization_required}
              onChange={(event) =>
                setForm({ ...form, authorization_required: event.target.checked })
              }
              className="h-4 w-4 rounded border-slate-300"
            />
            Requiere autorizacion previa
          </label>

          <FormError message={error} />

          <div className="flex justify-end gap-3">
            {editing && (
              <ActionButton tone="neutral" onClick={reset}>
                Cancelar edicion
              </ActionButton>
            )}
            <ActionButton tone="primary" type="submit" disabled={isSaving}>
              <Plus className="h-4 w-4" />
              {isSaving ? 'Guardando...' : editing ? 'Guardar cambios' : 'Agregar cobertura'}
            </ActionButton>
          </div>
        </form>
      </div>
    </Modal>
  );
}
