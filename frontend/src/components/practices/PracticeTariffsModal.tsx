import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPractices } from '@/api/endpoints/practices/practices';
import { getRegistry } from '@/api/endpoints/registry/registry';
import type {
  MedicalPracticeRead,
  MedicalPracticeTariffCreate,
  MedicalPracticeTariffRead,
} from '@/api/model';
import Modal from '@/components/Modal';
import {
  ActionButton,
  EmptyState,
  Field,
  FormError,
  Spinner,
  inputClass,
} from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { money, period, units } from './labels';

type TariffForm = {
  payer_id: string;
  health_plan_id: string;
  unit_value: string;
  professional_fee: string;
  expense_amount: string;
  total_amount: string;
  coinsurance: string;
  valid_from: string;
  valid_until: string;
  notes: string;
};

const emptyForm: TariffForm = {
  payer_id: '',
  health_plan_id: '',
  unit_value: '',
  professional_fee: '',
  expense_amount: '',
  total_amount: '',
  coinsurance: '',
  valid_from: new Date().toISOString().slice(0, 10),
  valid_until: '',
  notes: '',
};

/** Empty inputs travel as null so the API derives the amounts from the units. */
function toPayload(form: TariffForm): MedicalPracticeTariffCreate {
  const decimal = (value: string) => (value.trim() === '' ? null : value.trim());
  return {
    payer_id: form.payer_id || null,
    health_plan_id: form.health_plan_id || null,
    unit_value: decimal(form.unit_value),
    professional_fee: decimal(form.professional_fee),
    expense_amount: decimal(form.expense_amount),
    total_amount: decimal(form.total_amount),
    coinsurance: decimal(form.coinsurance) ?? '0',
    currency: 'ARS',
    valid_from: form.valid_from,
    valid_until: form.valid_until || null,
    notes: form.notes.trim() || null,
  };
}

function toForm(tariff: MedicalPracticeTariffRead): TariffForm {
  return {
    payer_id: tariff.payer_id ?? '',
    health_plan_id: tariff.health_plan_id ?? '',
    unit_value: tariff.unit_value ?? '',
    professional_fee: tariff.professional_fee,
    expense_amount: tariff.expense_amount,
    total_amount: tariff.total_amount,
    coinsurance: tariff.coinsurance,
    valid_from: tariff.valid_from,
    valid_until: tariff.valid_until ?? '',
    notes: tariff.notes ?? '',
  };
}

export default function PracticeTariffsModal({
  practice,
  open,
  onClose,
}: {
  practice: MedicalPracticeRead | null;
  open: boolean;
  onClose: () => void;
}) {
  const api = getPractices();
  const registry = getRegistry();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<TariffForm>(emptyForm);
  const [editing, setEditing] = useState<MedicalPracticeTariffRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  const practiceId = practice?.id ?? '';

  const tariffsQuery = useQuery({
    queryKey: ['practice-tariffs', practiceId],
    queryFn: () => api.listPracticeTariffsApiV1PracticesPracticeIdTariffsGet(practiceId),
    enabled: open && practiceId !== '',
  });

  const payersQuery = useQuery({
    queryKey: ['payers'],
    queryFn: () => registry.listPayersApiV1PayersGet(),
    enabled: open,
  });

  const plansQuery = useQuery({
    queryKey: ['health-plans', form.payer_id],
    queryFn: () => registry.listPayerHealthPlansApiV1PayersPayerIdHealthPlansGet(form.payer_id),
    enabled: open && form.payer_id !== '',
  });

  const reset = () => {
    setForm(emptyForm);
    setEditing(null);
    setError(null);
  };

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['practice-tariffs', practiceId] });
  };

  const createMutation = useMutation({
    mutationFn: (data: MedicalPracticeTariffCreate) =>
      api.createPracticeTariffApiV1PracticesPracticeIdTariffsPost(practiceId, data),
    onSuccess: () => {
      invalidate();
      reset();
    },
    onError: (mutationError) =>
      setError(apiErrorMessage(mutationError, 'No se pudo guardar el valor.')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ tariffId, data }: { tariffId: string; data: MedicalPracticeTariffCreate }) =>
      api.updatePracticeTariffApiV1PracticesPracticeIdTariffsTariffIdPut(
        practiceId,
        tariffId,
        data,
      ),
    onSuccess: () => {
      invalidate();
      reset();
    },
    onError: (mutationError) =>
      setError(apiErrorMessage(mutationError, 'No se pudo guardar el valor.')),
  });

  const deleteMutation = useMutation({
    mutationFn: (tariffId: string) =>
      api.deletePracticeTariffApiV1PracticesPracticeIdTariffsTariffIdDelete(practiceId, tariffId),
    onSuccess: invalidate,
    onError: (mutationError) =>
      setError(apiErrorMessage(mutationError, 'No se pudo eliminar el valor.')),
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const data = toPayload(form);
    if (editing) {
      updateMutation.mutate({ tariffId: editing.id, data });
      return;
    }
    createMutation.mutate(data);
  };

  const handleDelete = (tariff: MedicalPracticeTariffRead) => {
    if (!window.confirm('Eliminar este valor?')) return;
    setError(null);
    deleteMutation.mutate(tariff.id);
  };

  const payers = payersQuery.data ?? [];
  const plans = plansQuery.data ?? [];
  const tariffs = tariffsQuery.data ?? [];
  const isSaving = createMutation.isPending || updateMutation.isPending;

  const payerName = (tariff: MedicalPracticeTariffRead) => {
    if (!tariff.payer_id) return 'Institucional / particular';
    return payers.find((payer) => payer.id === tariff.payer_id)?.name ?? 'Financiador';
  };

  const closeModal = () => {
    reset();
    onClose();
  };

  if (!practice) return null;

  return (
    <Modal
      open={open}
      onClose={closeModal}
      title={`Valores de ${practice.code} - ${practice.name}`}
      maxWidth="max-w-4xl"
    >
      <div className="space-y-6">
        <p className="rounded-lg bg-slate-50 px-4 py-3 text-xs text-slate-500">
          La practica tiene {units(practice.galeno_units)} unidades galeno de honorarios y{' '}
          {units(practice.expense_units)} de gastos. Si informa el valor de la unidad, los
          importes se calculan con esas unidades. El valor del plan prevalece sobre el del
          financiador, y el del financiador sobre el institucional.
        </p>

        {tariffsQuery.isLoading && <Spinner />}
        {tariffs.length === 0 && !tariffsQuery.isLoading && (
          <EmptyState message="La practica todavia no tiene valores cargados." />
        )}

        {tariffs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Cobertura</th>
                  <th className="px-3 py-2 text-right font-semibold">Unidad</th>
                  <th className="px-3 py-2 text-right font-semibold">Honorarios</th>
                  <th className="px-3 py-2 text-right font-semibold">Gastos</th>
                  <th className="px-3 py-2 text-right font-semibold">Total</th>
                  <th className="px-3 py-2 text-right font-semibold">Coseguro</th>
                  <th className="px-3 py-2 text-left font-semibold">Vigencia</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {tariffs.map((tariff) => (
                  <tr key={tariff.id} className="hover:bg-slate-50">
                    <td className="px-3 py-2">
                      <p className="font-semibold text-slate-700">{payerName(tariff)}</p>
                      {tariff.health_plan_id && (
                        <p className="text-xs text-slate-400">
                          Plan{' '}
                          {plans.find((plan) => plan.id === tariff.health_plan_id)?.name ??
                            tariff.health_plan_id.slice(0, 8)}
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-600">
                      {money(tariff.unit_value, tariff.currency)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-600">
                      {money(tariff.professional_fee, tariff.currency)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-600">
                      {money(tariff.expense_amount, tariff.currency)}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold text-slate-800">
                      {money(tariff.total_amount, tariff.currency)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-600">
                      {money(tariff.coinsurance, tariff.currency)}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {period(tariff.valid_from, tariff.valid_until)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => {
                            setEditing(tariff);
                            setForm(toForm(tariff));
                            setError(null);
                          }}
                          className="rounded-lg p-2 text-slate-500 hover:bg-teal-50 hover:text-teal-700"
                          title="Editar valor"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(tariff)}
                          disabled={deleteMutation.isPending}
                          className="rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                          title="Eliminar valor"
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

        <form onSubmit={handleSubmit} className="space-y-4 border-t border-slate-100 pt-5">
          <h3 className="text-sm font-bold text-slate-700">
            {editing ? 'Editar valor' : 'Nuevo valor'}
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Financiador">
              <select
                value={form.payer_id}
                onChange={(event) =>
                  setForm({ ...form, payer_id: event.target.value, health_plan_id: '' })
                }
                className={inputClass}
              >
                <option value="">Institucional / particular</option>
                {payers.map((payer) => (
                  <option key={payer.id} value={payer.id}>
                    {payer.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Plan">
              <select
                value={form.health_plan_id}
                onChange={(event) => setForm({ ...form, health_plan_id: event.target.value })}
                disabled={form.payer_id === ''}
                className={inputClass}
              >
                <option value="">Todos los planes del financiador</option>
                {plans.map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Valor de la unidad">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.unit_value}
                onChange={(event) => setForm({ ...form, unit_value: event.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label="Coseguro a cargo del paciente">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.coinsurance}
                onChange={(event) => setForm({ ...form, coinsurance: event.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label="Honorarios">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.professional_fee}
                onChange={(event) => setForm({ ...form, professional_fee: event.target.value })}
                placeholder="Se calcula con las unidades"
                className={inputClass}
              />
            </Field>
            <Field label="Gastos">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.expense_amount}
                onChange={(event) => setForm({ ...form, expense_amount: event.target.value })}
                placeholder="Se calcula con las unidades"
                className={inputClass}
              />
            </Field>
            <Field label="Total (importe cerrado)">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.total_amount}
                onChange={(event) => setForm({ ...form, total_amount: event.target.value })}
                placeholder="Honorarios + gastos"
                className={inputClass}
              />
            </Field>
            <Field label="Vigente desde">
              <input
                type="date"
                required
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
            <Field label="Observaciones">
              <input
                type="text"
                value={form.notes}
                onChange={(event) => setForm({ ...form, notes: event.target.value })}
                className={inputClass}
              />
            </Field>
          </div>

          <FormError message={error} />

          <div className="flex justify-end gap-3">
            {editing && (
              <ActionButton onClick={reset} tone="neutral">
                Cancelar edicion
              </ActionButton>
            )}
            <ActionButton type="submit" tone="primary" disabled={isSaving}>
              {editing ? <Pencil className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              {isSaving ? 'Guardando...' : 'Guardar valor'}
            </ActionButton>
          </div>
        </form>
      </div>
    </Modal>
  );
}
