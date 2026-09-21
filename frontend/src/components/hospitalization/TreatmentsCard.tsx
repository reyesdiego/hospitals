import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getTreatments } from '@/api/endpoints/treatments/treatments';
import type {
  HospitalizationRead,
  MedicationRoute,
  ScheduleKind,
  TreatmentKind,
  TreatmentRead,
} from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import { useAuth } from '@/auth/AuthContext';
import { isPostDischarge } from './lock';
import Modal from '@/components/Modal';
import AdministrationsPanel from './AdministrationsPanel';
import ProfessionalPicker from '@/components/professionals/ProfessionalPicker';
import {
  ActionButton,
  Badge,
  Card,
  Field,
  FormError,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import {
  MEDICATION_ROUTE_LABELS,
  SCHEDULE_KIND_LABELS,
  TREATMENT_KIND_LABELS,
  TREATMENT_STATUS_COLORS,
  TREATMENT_STATUS_LABELS,
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, Pencil, Pill, Plus } from 'lucide-react';

type TreatmentForm = {
  kind: TreatmentKind;
  description: string;
  presentation: string;
  dose: string;
  route: '' | MedicationRoute;
  frequency: string;
  schedule_kind: ScheduleKind;
  interval_hours: string;
  /** Horarios fijos en "HH:MM", separados por coma: 08:00, 20:00. */
  times_of_day: string;
  prescribed_by_id: string;
  indication: string;
};

const emptyForm: TreatmentForm = {
  kind: 'MEDICATION',
  description: '',
  presentation: '',
  dose: '',
  route: '',
  frequency: '',
  schedule_kind: 'AS_NEEDED',
  interval_hours: '',
  times_of_day: '',
  prescribed_by_id: '',
  indication: '',
};

export function TreatmentsCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getTreatments();
  const queryClient = useQueryClient();
  const { user, can } = useAuth();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TreatmentRead | null>(null);
  const [form, setForm] = useState<TreatmentForm>(emptyForm);
  const [stopping, setStopping] = useState<TreatmentRead | null>(null);
  const [stopStatus, setStopStatus] = useState<'SUSPENDED' | 'COMPLETED'>('SUSPENDED');
  const [stopReason, setStopReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const treatmentsQuery = useQuery({
    queryKey: ['treatments', hosp.id],
    queryFn: () => api.listTreatmentsApiV1HospitalizationsHospitalizationIdTreatmentsGet(hosp.id),
  });

  const done = () => {
    invalidateHospitalization(queryClient, hosp.id);
    queryClient.invalidateQueries({ queryKey: ['treatments', hosp.id] });
    setError(null);
  };

  const closeModal = () => {
    setOpen(false);
    setEditing(null);
    setForm(emptyForm);
  };

  const payload = () => ({
    description: form.description.trim(),
    presentation: form.presentation.trim() || null,
    dose: form.dose.trim() || null,
    route: form.route || null,
    // Vacia: la escribe el backend desde el esquema.
    frequency: form.frequency.trim() || null,
    schedule_kind: form.schedule_kind,
    interval_hours:
      form.schedule_kind === 'INTERVAL' && form.interval_hours
        ? Number(form.interval_hours)
        : null,
    times_of_day:
      form.schedule_kind === 'TIMES'
        ? form.times_of_day
            .split(',')
            .map((value) => value.trim())
            .filter(Boolean)
            .map((value) => (value.length === 5 ? `${value}:00` : value))
        : null,
    prescribed_by_id: form.prescribed_by_id || null,
    indication: form.indication.trim() || null,
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      editing
        ? api.updateTreatmentApiV1HospitalizationsHospitalizationIdTreatmentsTreatmentIdPut(
            hosp.id,
            editing.id,
            payload(),
          )
        : api.addTreatmentApiV1HospitalizationsHospitalizationIdTreatmentsPost(hosp.id, {
            kind: form.kind,
            ...payload(),
          }),
    onSuccess: () => {
      done();
      closeModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar la indicacion.')),
  });

  const stopMutation = useMutation({
    mutationFn: () =>
      api.stopTreatmentApiV1HospitalizationsHospitalizationIdTreatmentsTreatmentIdStopPost(
        hosp.id,
        stopping!.id,
        { status: stopStatus, reason: stopReason.trim() || null },
      ),
    onSuccess: () => {
      done();
      setStopping(null);
      setStopReason('');
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo cerrar la indicacion.')),
  });

  const treatments = treatmentsQuery.data ?? [];
  // Con el alta medica dada la internacion queda cerrada a cambios, salvo para un admin.
  const canEdit = canManage && (!isPostDischarge(hosp.status) || user?.role === 'ADMIN');
  // Las tomas las registra enfermeria, que no maneja el resto de la internacion.
  const canRecordDoses =
    (can('NURSING_TASKS') || canManage) &&
    (!isPostDischarge(hosp.status) || user?.role === 'ADMIN');

  const openCreate = (kind: TreatmentKind) => {
    setEditing(null);
    setForm({ ...emptyForm, kind });
    setError(null);
    setOpen(true);
  };

  const openEdit = (item: TreatmentRead) => {
    setEditing(item);
    setForm({
      kind: item.kind,
      description: item.description,
      presentation: item.presentation ?? '',
      dose: item.dose ?? '',
      route: item.route ?? '',
      frequency: item.frequency ?? '',
      schedule_kind: item.schedule_kind,
      interval_hours: item.interval_hours ? String(item.interval_hours) : '',
      times_of_day: (item.times_of_day ?? [])
        .map((value) => value.slice(0, 5))
        .join(', '),
      prescribed_by_id: item.prescribed_by_id ?? '',
      indication: item.indication ?? '',
    });
    setError(null);
    setOpen(true);
  };

  return (
    <Card className="p-6">
      <SectionTitle icon={<Pill className="h-5 w-5 text-teal-600" />}>
        Medicacion y tratamiento
      </SectionTitle>

      {treatments.length === 0 ? (
        <p className="text-sm text-slate-400">
          No hay medicacion ni tratamientos indicados en esta internacion.
        </p>
      ) : (
        <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
          {treatments.map((item) => {
            const closed = item.status !== 'ACTIVE';
            return (
              <div
                key={item.id}
                className={`flex flex-wrap items-start justify-between gap-3 px-4 py-3 ${
                  closed ? 'bg-slate-50/60' : ''
                }`}
              >
                <div>
                  <p className={`text-sm font-semibold ${closed ? 'text-slate-400' : 'text-slate-700'}`}>
                    {item.description}
                    {item.presentation ? ` - ${item.presentation}` : ''}
                  </p>
                  <p className="text-xs text-slate-500">
                    {[
                      TREATMENT_KIND_LABELS[item.kind],
                      item.dose,
                      item.route ? MEDICATION_ROUTE_LABELS[item.route] : null,
                      item.frequency,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  <p className="text-xs text-slate-400">
                    Desde {formatDateTime(item.started_at)}
                    {item.ended_at ? ` · hasta ${formatDateTime(item.ended_at)}` : ''}
                    {item.recorded_by_user_name ? ` · ${item.recorded_by_user_name}` : ''}
                  </p>
                  {item.indication && (
                    <p className="text-xs text-slate-500">{item.indication}</p>
                  )}
                  {item.end_reason && (
                    <p className="text-xs font-medium text-amber-700">{item.end_reason}</p>
                  )}
                  <AdministrationsPanel
                    hospitalizationId={hosp.id}
                    treatment={item}
                    canRecord={canRecordDoses}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    status={TREATMENT_STATUS_LABELS[item.status]}
                    color={TREATMENT_STATUS_COLORS[item.status]}
                  />
                  {canEdit && !closed && (
                    <>
                      <button
                        type="button"
                        onClick={() => openEdit(item)}
                        className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                        title="Corregir indicacion"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setStopping(item);
                          setStopStatus('SUSPENDED');
                          setStopReason('');
                          setError(null);
                        }}
                        className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-amber-50 hover:text-amber-700"
                        title="Cerrar indicacion"
                      >
                        <Ban className="h-4 w-4" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <FormError message={error} />

      {canEdit && (
        <div className="mt-4 flex flex-wrap justify-end gap-3">
          <ActionButton tone="teal" onClick={() => openCreate('TREATMENT')}>
            <Plus className="h-4 w-4" />
            Indicar tratamiento
          </ActionButton>
          <ActionButton tone="primary" onClick={() => openCreate('MEDICATION')}>
            <Plus className="h-4 w-4" />
            Indicar medicacion
          </ActionButton>
        </div>
      )}

      <Modal
        open={open}
        onClose={closeModal}
        title={
          editing
            ? `Corregir ${TREATMENT_KIND_LABELS[editing.kind].toLowerCase()}`
            : `Indicar ${TREATMENT_KIND_LABELS[form.kind].toLowerCase()}`
        }
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            saveMutation.mutate();
          }}
        >
          <Field label={form.kind === 'MEDICATION' ? 'Droga' : 'Tratamiento'}>
            <input
              type="text"
              required
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              placeholder={
                form.kind === 'MEDICATION' ? 'Amoxicilina' : 'Kinesiologia respiratoria'
              }
              className={inputClass}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Presentacion">
              <input
                type="text"
                value={form.presentation}
                onChange={(event) => setForm({ ...form, presentation: event.target.value })}
                placeholder="500 mg comprimidos"
                className={inputClass}
              />
            </Field>
            <Field label="Dosis">
              <input
                type="text"
                value={form.dose}
                onChange={(event) => setForm({ ...form, dose: event.target.value })}
                placeholder="1 comprimido"
                className={inputClass}
              />
            </Field>
            <Field label="Via">
              <select
                value={form.route}
                onChange={(event) =>
                  setForm({ ...form, route: event.target.value as '' | MedicationRoute })
                }
                className={inputClass}
              >
                <option value="">Sin especificar</option>
                {Object.entries(MEDICATION_ROUTE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Esquema">
              <select
                value={form.schedule_kind}
                onChange={(event) =>
                  setForm({ ...form, schedule_kind: event.target.value as ScheduleKind })
                }
                className={inputClass}
              >
                {Object.entries(SCHEDULE_KIND_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          {form.schedule_kind === 'INTERVAL' && (
            <Field label="Cada cuantas horas">
              <input
                type="number"
                min="1"
                max="168"
                required
                value={form.interval_hours}
                onChange={(event) => setForm({ ...form, interval_hours: event.target.value })}
                placeholder="8"
                className={inputClass}
              />
            </Field>
          )}
          {form.schedule_kind === 'TIMES' && (
            <Field label="Horarios del dia (separados por coma)">
              <input
                type="text"
                required
                value={form.times_of_day}
                onChange={(event) => setForm({ ...form, times_of_day: event.target.value })}
                placeholder="08:00, 14:00, 20:00"
                className={inputClass}
              />
            </Field>
          )}
          {form.schedule_kind !== 'AS_NEEDED' && form.schedule_kind !== 'CONTINUOUS' && (
            <p className="text-xs text-slate-500">
              Con el esquema cargado, el panel de enfermeria calcula los horarios y marca
              las tomas vencidas.
            </p>
          )}

          <Field label="Indicada por">
            <ProfessionalPicker
              value={form.prescribed_by_id}
              onSelect={(id) => setForm({ ...form, prescribed_by_id: id })}
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
            <ActionButton type="submit" tone="primary" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={stopping !== null}
        onClose={() => setStopping(null)}
        title="Cerrar indicacion"
      >
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
            {stopping?.description}. Deja de darse desde ahora y queda registrada en la
            historia con su motivo.
          </p>
          <Field label="Como termina">
            <select
              value={stopStatus}
              onChange={(event) =>
                setStopStatus(event.target.value as 'SUSPENDED' | 'COMPLETED')
              }
              className={inputClass}
            >
              <option value="SUSPENDED">Suspendida antes de tiempo</option>
              <option value="COMPLETED">Cumplio el plan indicado</option>
            </select>
          </Field>
          <Field label="Motivo">
            <input
              type="text"
              value={stopReason}
              onChange={(event) => setStopReason(event.target.value)}
              placeholder="Mala tolerancia, cambio de esquema..."
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={() => setStopping(null)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="warning"
              disabled={stopMutation.isPending}
              onClick={() => stopMutation.mutate()}
            >
              {stopMutation.isPending ? 'Cerrando...' : 'Cerrar indicacion'}
            </ActionButton>
          </div>
        </div>
      </Modal>
    </Card>
  );
}

export default TreatmentsCard;
