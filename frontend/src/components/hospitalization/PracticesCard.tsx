import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getPractices } from '@/api/endpoints/practices/practices';
import type {
  HospitalizationPracticeCreate,
  HospitalizationPracticeRead,
  HospitalizationRead,
} from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Badge,
  Card,
  Field,
  FormError,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import { money } from '@/components/practices/labels';
import {
  PRACTICE_ORDER_STATUS_COLORS,
  PRACTICE_ORDER_STATUS_LABELS,
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, CheckCircle2, ClipboardList, Plus } from 'lucide-react';

/** Mientras la internación está abierta se pueden indicar y realizar prácticas. */
const OPEN_STATUSES = [
  'PENDING_BED',
  'IN_PROGRESS',
  'DISCHARGE_PLANNED',
  'CLINICALLY_DISCHARGED',
];

type PracticeForm = {
  practice_id: string;
  prescribed_by_id: string;
  performed_by_id: string;
  quantity: string;
  performed: boolean;
  performed_at: string;
  unit_price: string;
  indication: string;
};

const emptyForm: PracticeForm = {
  practice_id: '',
  prescribed_by_id: '',
  performed_by_id: '',
  quantity: '1',
  performed: true,
  performed_at: '',
  unit_price: '',
  indication: '',
};

/** El input ``datetime-local`` no lleva zona; se envía el instante local como ISO. */
function toIso(value: string): string {
  return new Date(value).toISOString();
}

export function PracticesCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getPractices();
  const defaultApi = getDefault();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<PracticeForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const practicesQuery = useQuery({
    queryKey: ['hospitalization-practices', hosp.id],
    queryFn: () =>
      api.listHospitalizationPracticesApiV1HospitalizationsHospitalizationIdPracticesGet(hosp.id),
    retry: false,
  });
  const catalogQuery = useQuery({
    queryKey: ['practices', { only_active: true }],
    queryFn: () => api.listPracticesApiV1PracticesGet({ only_active: true }),
    enabled: open,
  });
  const professionalsQuery = useQuery({
    queryKey: ['professionals'],
    queryFn: () => defaultApi.listProfessionalsApiV1ProfessionalsGet(),
  });

  const closeModal = () => {
    setOpen(false);
    setForm(emptyForm);
    setError(null);
  };

  const registerMutation = useMutation({
    mutationFn: (data: HospitalizationPracticeCreate) =>
      api.registerHospitalizationPracticeApiV1HospitalizationsHospitalizationIdPracticesPost(
        hosp.id,
        data,
      ),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      closeModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar la practica.')),
  });

  const performMutation = useMutation({
    mutationFn: (orderId: string) =>
      api.performHospitalizationPracticeApiV1HospitalizationsHospitalizationIdPracticesOrderIdPerformPost(
        hosp.id,
        orderId,
        {},
      ),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar la realizacion.')),
  });

  const cancelMutation = useMutation({
    mutationFn: (orderId: string) =>
      api.cancelHospitalizationPracticeApiV1HospitalizationsHospitalizationIdPracticesOrderIdCancelPost(
        hosp.id,
        orderId,
        {},
      ),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo anular la practica.')),
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const performedAt = form.performed
      ? form.performed_at
        ? toIso(form.performed_at)
        : new Date().toISOString()
      : null;
    registerMutation.mutate({
      practice_id: form.practice_id,
      prescribed_by_id: form.prescribed_by_id,
      performed_by_id: form.performed && form.performed_by_id ? form.performed_by_id : null,
      quantity: form.quantity.trim() === '' ? '1' : form.quantity.trim(),
      performed_at: performedAt,
      unit_price: form.unit_price.trim() === '' ? null : form.unit_price.trim(),
      indication: form.indication.trim() || null,
    });
  };

  const practices = practicesQuery.data ?? [];
  const professionals = professionalsQuery.data ?? [];
  const professionalName = (id: string | null) => {
    if (!id) return null;
    const professional = professionals.find((item) => item.id === id);
    return professional ? `${professional.last_name}, ${professional.first_name}` : 'Profesional';
  };

  const charged = practices.reduce(
    (total, practice) => total + Number(practice.charge?.amount ?? 0),
    0,
  );
  const isOpen = OPEN_STATUSES.includes(hosp.status);
  /** Indicada, o realizada con el cargo anulado: en ambos casos falta facturarla. */
  const isPending = (practice: HospitalizationPracticeRead) =>
    practice.status === 'REQUESTED' ||
    (practice.status === 'PERFORMED' && practice.charge?.status === 'VOID');
  const quantityOf = (practice: HospitalizationPracticeRead) => Number(practice.quantity);

  return (
    <Card className="p-6">
      <SectionTitle icon={<ClipboardList className="h-5 w-5 text-teal-600" />}>
        Practicas de la internacion
      </SectionTitle>

      {practices.length === 0 ? (
        <p className="text-sm text-slate-400">
          Todavia no se registraron practicas en esta internacion.
        </p>
      ) : (
        <div className="space-y-3">
          {practices.map((practice) => (
            <div key={practice.id} className="rounded-lg border border-slate-100 bg-slate-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-800">
                    {practice.practice_code} - {practice.practice_name}
                    {quantityOf(practice) !== 1 && (
                      <span className="ml-2 text-xs font-medium text-slate-500">
                        x{quantityOf(practice)}
                      </span>
                    )}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Recetada por {professionalName(practice.prescribed_by_id) ?? 'profesional'} ·{' '}
                    {formatDateTime(practice.prescribed_at)}
                  </p>
                  {practice.performed_at && (
                    <p className="text-xs text-slate-500">
                      Realizada {formatDateTime(practice.performed_at)}
                      {practice.performed_by_id
                        ? ` por ${professionalName(practice.performed_by_id)}`
                        : ''}
                    </p>
                  )}
                  {practice.indication && (
                    <p className="mt-1 text-xs italic text-slate-500">{practice.indication}</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <Badge
                    status={PRACTICE_ORDER_STATUS_LABELS[practice.status]}
                    color={PRACTICE_ORDER_STATUS_COLORS[practice.status]}
                  />
                  {practice.charge && (
                    <div className="text-right">
                      <p
                        className={`text-sm font-bold ${
                          practice.charge.status === 'VOID'
                            ? 'text-slate-400 line-through'
                            : 'text-slate-700'
                        }`}
                      >
                        {money(practice.charge.amount)}
                      </p>
                      {practice.charge.status === 'VOID' && (
                        <p className="text-xs font-semibold text-red-500">Cargo anulado</p>
                      )}
                    </div>
                  )}
                  {canManage && isOpen && isPending(practice) && (
                    <div className="flex gap-2">
                      <ActionButton
                        tone="success"
                        onClick={() => performMutation.mutate(practice.id)}
                        disabled={performMutation.isPending}
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        {practice.status === 'PERFORMED' ? 'Volver a facturar' : 'Realizada'}
                      </ActionButton>
                      <ActionButton
                        tone="danger"
                        onClick={() => cancelMutation.mutate(practice.id)}
                        disabled={cancelMutation.isPending}
                      >
                        <Ban className="h-4 w-4" />
                        Anular
                      </ActionButton>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          <div className="flex justify-between rounded-lg bg-white px-4 py-3 text-sm">
            <span className="font-medium text-slate-500">Cargado a la cuenta</span>
            <span className="font-bold text-slate-800">{money(charged.toFixed(2))}</span>
          </div>
        </div>
      )}

      <FormError message={error} />

      {canManage && isOpen && (
        <div className="mt-4 flex justify-end">
          <ActionButton tone="primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" />
            Agregar practica
          </ActionButton>
        </div>
      )}

      <Modal open={open} onClose={closeModal} title="Practica de la internacion" maxWidth="max-w-xl">
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Practica del nomenclador">
            <select
              required
              value={form.practice_id}
              onChange={(event) => setForm({ ...form, practice_id: event.target.value })}
              className={inputClass}
            >
              <option value="">Seleccione una practica</option>
              {(catalogQuery.data ?? []).map((practice) => (
                <option key={practice.id} value={practice.id}>
                  {practice.code} - {practice.name}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Recetada por">
            <select
              required
              value={form.prescribed_by_id}
              onChange={(event) => setForm({ ...form, prescribed_by_id: event.target.value })}
              className={inputClass}
            >
              <option value="">Seleccione un profesional</option>
              {professionals.map((professional) => (
                <option key={professional.id} value={professional.id}>
                  {professional.last_name}, {professional.first_name}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Cantidad">
            <input
              type="number"
              step="0.001"
              min="0.001"
              value={form.quantity}
              onChange={(event) => setForm({ ...form, quantity: event.target.value })}
              className={inputClass}
            />
          </Field>

          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.performed}
              onChange={(event) => setForm({ ...form, performed: event.target.checked })}
              className="h-4 w-4 rounded border-slate-300"
            />
            Ya realizada (genera el cargo en la cuenta)
          </label>

          {form.performed && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Fecha y hora de realizacion">
                <input
                  type="datetime-local"
                  value={form.performed_at}
                  onChange={(event) => setForm({ ...form, performed_at: event.target.value })}
                  className={inputClass}
                />
              </Field>
              <Field label="Realizada por">
                <select
                  value={form.performed_by_id}
                  onChange={(event) => setForm({ ...form, performed_by_id: event.target.value })}
                  className={inputClass}
                >
                  <option value="">Sin registrar</option>
                  {professionals.map((professional) => (
                    <option key={professional.id} value={professional.id}>
                      {professional.last_name}, {professional.first_name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          )}

          <Field label="Importe unitario (solo si la practica no tiene valor acordado)">
            <input
              type="number"
              step="0.01"
              min="0"
              value={form.unit_price}
              onChange={(event) => setForm({ ...form, unit_price: event.target.value })}
              placeholder="Se toma del valor vigente para la cobertura"
              className={inputClass}
            />
          </Field>

          <Field label="Indicacion">
            <textarea
              rows={2}
              value={form.indication}
              onChange={(event) => setForm({ ...form, indication: event.target.value })}
              className={inputClass}
            />
          </Field>

          <FormError message={error} />

          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={closeModal}>
              Cancelar
            </ActionButton>
            <ActionButton type="submit" tone="primary" disabled={registerMutation.isPending}>
              {registerMutation.isPending ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

export default PracticesCard;
