import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getNursing } from '@/api/endpoints/nursing/nursing';
import { getTreatments } from '@/api/endpoints/treatments/treatments';
import type { DoseSlotRead, MedicationRoundRead } from '@/api/model';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Card,
  EmptyState,
  Field,
  FormError,
  SectionTitle,
  Spinner,
  inputClass,
} from '@/components/ui';
import {
  MEDICATION_ROUTE_LABELS,
  SCHEDULE_KIND_LABELS,
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, Check, Clock, Pill } from 'lucide-react';

/** La ventana del timeline: el turno que se esta haciendo y el que viene. */
const HOURS_BACK = 6;
const HOURS_AHEAD = 12;

const SLOT_STYLES: Record<DoseSlotRead['state'], string> = {
  GIVEN: 'bg-emerald-500',
  OMITTED: 'bg-slate-400',
  PENDING: 'bg-teal-200',
  OVERDUE: 'bg-amber-500',
};

const SLOT_LABELS: Record<DoseSlotRead['state'], string> = {
  GIVEN: 'Dada',
  OMITTED: 'No se dio',
  PENDING: 'Pendiente',
  OVERDUE: 'Vencida',
};

const hhmm = (value: string) =>
  new Date(value).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

/**
 * Linea de tiempo de la medicacion: cada fila es una indicacion y cada punto una toma,
 * ubicada en la hora que le corresponde. Verde lo dado, ambar lo vencido, celeste lo que
 * viene.
 */
export default function MedicationTimeline({ serviceId }: { serviceId?: string }) {
  const nursing = getNursing();
  const treatments = getTreatments();
  const queryClient = useQueryClient();
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [omitting, setOmitting] = useState<MedicationRoundRead | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  // La ventana se fija al montar: si se recalculara en cada render, las barras se moverian.
  const [start, end] = useMemo(() => {
    const now = new Date();
    const from = new Date(now.getTime() - HOURS_BACK * 3600_000);
    from.setMinutes(0, 0, 0);
    const to = new Date(now.getTime() + HOURS_AHEAD * 3600_000);
    to.setMinutes(0, 0, 0);
    return [from, to];
  }, []);

  const roundQuery = useQuery({
    queryKey: ['medication-round', serviceId ?? '', overdueOnly, start.toISOString()],
    queryFn: () =>
      nursing.listMedicationRoundApiV1NursingMedicationsGet({
        service_id: serviceId || undefined,
        overdue_only: overdueOnly,
        window_start: start.toISOString(),
        window_end: end.toISOString(),
      }),
    refetchInterval: 60_000,
  });

  const done = () => {
    queryClient.invalidateQueries({ queryKey: ['medication-round'] });
    queryClient.invalidateQueries({ queryKey: ['administrations'] });
    setError(null);
  };

  const registerMutation = useMutation({
    mutationFn: ({
      item,
      omissionReason,
    }: {
      item: MedicationRoundRead;
      omissionReason?: string;
    }) =>
      treatments.registerAdministrationApiV1HospitalizationsHospitalizationIdTreatmentsTreatmentIdAdministrationsPost(
        item.hospitalization_id,
        item.treatment_id,
        omissionReason
          ? { status: 'OMITTED', omission_reason: omissionReason }
          : { status: 'GIVEN' },
      ),
    onSuccess: () => {
      done();
      setOmitting(null);
      setReason('');
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar la toma.')),
  });

  const rounds = roundQuery.data ?? [];
  const overdue = rounds.filter((item) => item.overdue).length;
  const span = end.getTime() - start.getTime();
  /** Donde cae un horario dentro de la barra, en porcentaje. */
  const position = (value: string) =>
    Math.min(100, Math.max(0, ((new Date(value).getTime() - start.getTime()) / span) * 100));
  const nowLeft = position(new Date().toISOString());

  const hours = useMemo(() => {
    const marks: Date[] = [];
    const cursor = new Date(start);
    while (cursor <= end) {
      marks.push(new Date(cursor));
      cursor.setHours(cursor.getHours() + 3);
    }
    return marks;
  }, [start, end]);

  return (
    <Card className="mb-4 p-6">
      <SectionTitle icon={<Pill className="h-5 w-5 text-teal-600" />}>
        Linea de tiempo de medicacion
      </SectionTitle>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          Desde las {hhmm(start.toISOString())} hasta las {hhmm(end.toISOString())}
          {overdue > 0 ? ` · ${overdue} indicacion(es) vencida(s)` : ' · nada vencido'}
        </p>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(event) => setOverdueOnly(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Solo lo vencido
        </label>
      </div>

      {roundQuery.isLoading && <Spinner />}
      {!roundQuery.isLoading && rounds.length === 0 && (
        <EmptyState
          message={
            overdueOnly
              ? 'No hay medicacion vencida.'
              : 'No hay medicacion ni tratamientos activos.'
          }
        />
      )}

      {rounds.length > 0 && (
        <>
          {/* Regla de horas */}
          <div className="relative mb-1 ml-[260px] h-4 text-[10px] text-slate-400">
            {hours.map((hour) => (
              <span
                key={hour.toISOString()}
                className="absolute -translate-x-1/2"
                style={{ left: `${position(hour.toISOString())}%` }}
              >
                {hhmm(hour.toISOString())}
              </span>
            ))}
          </div>

          <div className="space-y-2">
            {rounds.map((item) => (
              <div
                key={item.treatment_id}
                className={`flex flex-wrap items-center gap-3 rounded-lg px-2 py-2 sm:flex-nowrap ${
                  item.overdue ? 'bg-amber-50/70' : 'hover:bg-slate-50'
                }`}
              >
                <div className="w-[250px] shrink-0">
                  <p className="truncate text-sm font-semibold text-slate-700">
                    {item.description}
                    {item.dose ? ` · ${item.dose}` : ''}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    <Link
                      to={`/hospitalizations/${item.hospitalization_id}`}
                      className="font-medium text-teal-700 hover:underline"
                    >
                      {item.patient_name}
                    </Link>
                    {item.bed_code ? ` · Cama ${item.bed_code}` : ''}
                  </p>
                  <p className="truncate text-xs text-slate-400">
                    {[
                      item.frequency || SCHEDULE_KIND_LABELS[item.schedule_kind],
                      item.route ? MEDICATION_ROUTE_LABELS[item.route] : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </div>

                <div className="relative h-9 min-w-[200px] flex-1 rounded-lg bg-slate-100">
                  {/* Ahora */}
                  <span
                    className="absolute top-0 h-full w-px bg-slate-400"
                    style={{ left: `${nowLeft}%` }}
                  />
                  {item.slots.map((slot, index) => (
                    <span
                      key={`${slot.due_at}-${index}`}
                      title={`${SLOT_LABELS[slot.state]} ${hhmm(slot.due_at)}${
                        slot.dose ? ` · ${slot.dose}` : ''
                      }${slot.reason ? ` · ${slot.reason}` : ''}`}
                      className={`absolute top-1/2 flex h-6 -translate-x-1/2 -translate-y-1/2 items-center rounded-full px-2 text-[10px] font-semibold text-white ${
                        SLOT_STYLES[slot.state]
                      } ${slot.state === 'PENDING' ? 'text-teal-900' : ''}`}
                      style={{ left: `${position(slot.due_at)}%` }}
                    >
                      {hhmm(slot.due_at)}
                    </span>
                  ))}
                  {item.slots.length === 0 && (
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
                      Sin horarios: {SCHEDULE_KIND_LABELS[item.schedule_kind].toLowerCase()}
                    </span>
                  )}
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {item.next_due_at && (
                    <span
                      className={`flex items-center gap-1 text-xs font-semibold ${
                        item.overdue ? 'text-amber-700' : 'text-slate-500'
                      }`}
                      title={formatDateTime(item.next_due_at) ?? ''}
                    >
                      <Clock className="h-3.5 w-3.5" />
                      {hhmm(item.next_due_at)}
                    </span>
                  )}
                  <ActionButton
                    tone="teal"
                    disabled={registerMutation.isPending}
                    onClick={() => registerMutation.mutate({ item })}
                  >
                    <Check className="h-4 w-4" />
                    Dada
                  </ActionButton>
                  <ActionButton
                    tone="warning"
                    onClick={() => {
                      setOmitting(item);
                      setReason('');
                      setError(null);
                    }}
                  >
                    <Ban className="h-4 w-4" />
                    No
                  </ActionButton>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
            {(['GIVEN', 'OMITTED', 'OVERDUE', 'PENDING'] as const).map((state) => (
              <span key={state} className="flex items-center gap-1.5">
                <span className={`h-2.5 w-2.5 rounded-full ${SLOT_STYLES[state]}`} />
                {SLOT_LABELS[state]}
              </span>
            ))}
          </div>
        </>
      )}

      <FormError message={error} />

      <Modal open={omitting !== null} onClose={() => setOmitting(null)} title="Toma no dada">
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
            {omitting?.description} · {omitting?.patient_name}. La omision queda registrada
            con su motivo: tambien es informacion clinica.
          </p>
          <Field label="Motivo">
            <input
              type="text"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Paciente en ayunas, rechazo la medicacion, no estaba en la cama..."
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={() => setOmitting(null)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="warning"
              disabled={registerMutation.isPending || reason.trim() === ''}
              onClick={() =>
                omitting &&
                registerMutation.mutate({ item: omitting, omissionReason: reason.trim() })
              }
            >
              {registerMutation.isPending ? 'Registrando...' : 'Registrar omision'}
            </ActionButton>
          </div>
        </div>
      </Modal>
    </Card>
  );
}
