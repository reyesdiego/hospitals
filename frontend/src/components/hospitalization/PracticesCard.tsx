import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getPractices } from '@/api/endpoints/practices/practices';
import type {
  HospitalizationPracticeCreate,
  HospitalizationPracticeRead,
  HospitalizationRead,
  MedicalPracticeRead,
  PlanCoverageCheckRead,
} from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import { useAuth } from '@/auth/AuthContext';
import { isPostDischarge } from './lock';
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
import PracticePicker from '@/components/practices/PracticePicker';
import ProfessionalPicker from '@/components/professionals/ProfessionalPicker';
import {
  PRACTICE_ORDER_STATUS_COLORS,
  PRACTICE_ORDER_STATUS_LABELS,
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, CheckCircle2, ClipboardList, Plus, ShieldAlert, ShieldCheck } from 'lucide-react';

/** Cómo se lee cada respuesta de la cartilla del plan. */
const COVERAGE_LABELS: Record<PlanCoverageCheckRead['status'], string> = {
  NO_COVERAGE: 'Paciente particular: no hay cartilla que aplicar.',
  NO_PLAN: 'La cobertura no esta vinculada a un plan del catalogo.',
  NO_CARTILLA: 'El plan no tiene cartilla cargada: no se aplican restricciones.',
  NOT_LISTED: 'La practica no esta en la cartilla del plan.',
  NOT_COVERED: 'El plan no cubre esta practica.',
  WAITING_PERIOD: 'La practica esta en carencia.',
  COVERED: 'Cubierta por el plan.',
};

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
  authorization_number: string;
  override: boolean;
  override_reason: string;
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
  authorization_number: '',
  override: false,
  override_reason: '',
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
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<PracticeForm>(emptyForm);
  /** La practica elegida en el buscador: el nomenclador no se trae entero. */
  const [practice, setPractice] = useState<MedicalPracticeRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  const practicesQuery = useQuery({
    queryKey: ['hospitalization-practices', hosp.id],
    queryFn: () =>
      api.listHospitalizationPracticesApiV1HospitalizationsHospitalizationIdPracticesGet(hosp.id),
    retry: false,
  });
  const professionalsQuery = useQuery({
    queryKey: ['professionals'],
    queryFn: () => defaultApi.listProfessionalsApiV1ProfessionalsGet(),
  });
  // Lo que dice la cartilla del plan sobre la practica elegida, antes de indicarla.
  const coverageQuery = useQuery({
    queryKey: ['practice-coverage-check', hosp.id, form.practice_id, form.performed_at],
    queryFn: () =>
      api.checkPracticeCoverageApiV1HospitalizationsHospitalizationIdPracticesCoverageCheckGet(
        hosp.id,
        {
          practice_id: form.practice_id,
          on: form.performed_at ? form.performed_at.slice(0, 10) : undefined,
        },
      ),
    enabled: open && form.practice_id !== '',
    retry: false,
  });

  const closeModal = () => {
    setOpen(false);
    setForm(emptyForm);
    setPractice(null);
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
      authorization_number: form.authorization_number.trim() || null,
      override_coverage_rules: form.override,
      override_reason: form.override ? form.override_reason.trim() || null : null,
    });
  };

  const practices = practicesQuery.data ?? [];
  const professionals = professionalsQuery.data ?? [];
  const coverage = form.practice_id ? coverageQuery.data : undefined;
  const nursingTask = Boolean(practice?.is_nursing_task);
  const professionalName = (id: string | null) => {
    if (!id) return null;
    const professional = professionals.find((item) => item.id === id);
    return professional ? `${professional.last_name}, ${professional.first_name}` : 'Profesional';
  };

  const charged = practices.reduce(
    (total, practice) => total + Number(practice.charge?.amount ?? 0),
    0,
  );
  // Con el alta medica dada la internacion queda cerrada a cambios, salvo para un admin.
  const locked = isPostDischarge(hosp.status);
  const isOpen =
    OPEN_STATUSES.includes(hosp.status) && (!locked || user?.role === 'ADMIN');
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
                  {/* Quien la dio por realizada en el sistema: en las tareas de enfermeria
                      es la enfermera que estuvo con el paciente. */}
                  {practice.performed_by_user_name && (
                    <p className="text-xs text-slate-500">
                      Aplicada por {practice.performed_by_user_name}
                    </p>
                  )}
                  {practice.indication && (
                    <p className="mt-1 text-xs italic text-slate-500">{practice.indication}</p>
                  )}
                  {Number(practice.copayment_amount) > 0 && (
                    <p className="text-xs text-slate-500">
                      Copago del plan {money(practice.copayment_amount)} por practica
                    </p>
                  )}
                  {practice.authorization_number && (
                    <p className="text-xs text-slate-500">
                      Autorizacion {practice.authorization_number}
                    </p>
                  )}
                  {practice.coverage_override_reason && (
                    <p className="mt-1 text-xs font-medium text-amber-600">
                      Fuera de cartilla: {practice.coverage_override_reason}
                    </p>
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
            {practice ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2">
                <p className="text-sm text-slate-700">
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold">
                    {practice.code}
                  </span>{' '}
                  {practice.name}
                  {practice.is_nursing_task && (
                    <span className="ml-1 text-xs text-teal-600">(enfermeria)</span>
                  )}
                </p>
                <ActionButton
                  tone="neutral"
                  onClick={() => {
                    setPractice(null);
                    setForm({ ...form, practice_id: '' });
                  }}
                >
                  Cambiar
                </ActionButton>
              </div>
            ) : (
              <PracticePicker
                onSelect={(selected) => {
                  setPractice(selected);
                  // Lo que ejecuta enfermeria se indica pendiente: lo aplica su panel.
                  setForm({
                    ...form,
                    practice_id: selected.id,
                    performed: selected.is_nursing_task ? false : form.performed,
                  });
                }}
              />
            )}
          </Field>

          {coverage && (
            <div
              className={`rounded-lg px-4 py-3 text-xs ${
                coverage.blocked
                  ? 'bg-red-50 text-red-700'
                  : coverage.status === 'COVERED' && !coverage.message
                    ? 'bg-emerald-50 text-emerald-700'
                    : coverage.message
                      ? 'bg-amber-50 text-amber-800'
                      : 'bg-slate-50 text-slate-500'
              }`}
            >
              <p className="flex items-center gap-1.5 font-semibold">
                {coverage.blocked ? (
                  <ShieldAlert className="h-4 w-4" />
                ) : (
                  <ShieldCheck className="h-4 w-4" />
                )}
                {coverage.message ?? COVERAGE_LABELS[coverage.status]}
              </p>
              {(Number(coverage.copayment_amount) > 0 ||
                coverage.requires_authorization ||
                coverage.waiting_period_days > 0) && (
                <p className="mt-1">
                  {coverage.waiting_period_days > 0 &&
                    `Carencia de ${coverage.waiting_period_days} dias` +
                      (coverage.available_from ? ` (cumplida el ${coverage.available_from})` : '') +
                      '. '}
                  {Number(coverage.copayment_amount) > 0 &&
                    `Copago de ${money(coverage.copayment_amount)} por practica. `}
                  {coverage.requires_authorization && 'Requiere autorizacion del financiador.'}
                </p>
              )}
            </div>
          )}

          {coverage?.requires_authorization && (
            <Field label="Numero de autorizacion del financiador">
              <input
                type="text"
                value={form.authorization_number}
                onChange={(event) =>
                  setForm({ ...form, authorization_number: event.target.value })
                }
                placeholder="El que dio el financiador"
                className={inputClass}
              />
            </Field>
          )}

          {coverage?.blocked && (
            <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <label className="flex items-center gap-2 text-sm font-medium text-amber-800">
                <input
                  type="checkbox"
                  checked={form.override}
                  onChange={(event) => setForm({ ...form, override: event.target.checked })}
                  className="h-4 w-4 rounded border-amber-300"
                />
                Registrar igual, fuera de la cartilla
              </label>
              {form.override && (
                <input
                  type="text"
                  required
                  value={form.override_reason}
                  onChange={(event) => setForm({ ...form, override_reason: event.target.value })}
                  placeholder="Motivo (queda asentado en la internacion)"
                  className={inputClass}
                />
              )}
            </div>
          )}

          <Field label="Recetada por">
            <ProfessionalPicker
              value={form.prescribed_by_id}
              onSelect={(id) => setForm({ ...form, prescribed_by_id: id })}
              emptyLabel=""
            />
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

          {nursingTask && !form.performed && (
            <p className="rounded-lg bg-teal-50 px-4 py-2.5 text-xs text-teal-700">
              La practica la ejecuta enfermeria: va a aparecer en su panel de tareas.
            </p>
          )}

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
                <ProfessionalPicker
                  value={form.performed_by_id}
                  onSelect={(id) => setForm({ ...form, performed_by_id: id })}
                />
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
            <ActionButton
              type="submit"
              tone="primary"
              disabled={
                registerMutation.isPending || !form.practice_id || !form.prescribed_by_id
              }
            >
              {registerMutation.isPending ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

export default PracticesCard;
