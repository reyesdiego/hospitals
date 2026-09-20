import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getNursing } from '@/api/endpoints/nursing/nursing';
import type { NursingTaskRead } from '@/api/model';
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
import {
  PRACTICE_ORDER_STATUS_COLORS,
  PRACTICE_ORDER_STATUS_LABELS,
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, BedDouble, CheckCircle2, ClipboardList, Syringe } from 'lucide-react';

/** Fecha local: ``toISOString`` da la de UTC y a la noche ya es el dia siguiente. */
const today = () => {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
};

/**
 * Lo que el medico indico y enfermeria tiene que hacerle al paciente: inyectables,
 * medicacion, extracciones, colocacion de Holter. Aplicar una tarea es registrar la practica
 * como realizada, con su cargo y su evento en la internacion.
 */
export default function NursingTasksPage() {
  const api = getNursing();
  const queryClient = useQueryClient();
  const [showResolved, setShowResolved] = useState(false);
  const [cancelling, setCancelling] = useState<NursingTaskRead | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const tasksQuery = useQuery({
    queryKey: ['nursing-tasks', showResolved],
    queryFn: () =>
      api.listNursingTasksApiV1NursingTasksGet(
        showResolved ? { pending_only: false, on: today() } : { pending_only: true },
      ),
    refetchInterval: 60_000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['nursing-tasks'] });
    queryClient.invalidateQueries({ queryKey: ['hospitalization-practices'] });
  };

  const performMutation = useMutation({
    mutationFn: (taskId: string) =>
      api.performNursingTaskApiV1NursingTasksOrderIdPerformPost(taskId, {}),
    onSuccess: () => {
      invalidate();
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar la aplicacion.')),
  });

  const cancelMutation = useMutation({
    mutationFn: ({ taskId, why }: { taskId: string; why: string }) =>
      api.cancelNursingTaskApiV1NursingTasksOrderIdCancelPost(taskId, { reason: why || null }),
    onSuccess: () => {
      invalidate();
      setCancelling(null);
      setReason('');
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo cancelar la tarea.')),
  });

  const tasks = tasksQuery.data ?? [];
  const pending = tasks.filter((task) => task.status === 'REQUESTED');
  // Agrupadas por sala: enfermeria recorre por sector, no por paciente suelto.
  const byWard = tasks.reduce<Record<string, NursingTaskRead[]>>((groups, task) => {
    const ward = task.ward ?? 'Sin cama asignada';
    groups[ward] = [...(groups[ward] ?? []), task];
    return groups;
  }, {});

  return (
    <div>
      <PageHeader
        title="Tareas de enfermeria"
        subtitle={
          showResolved
            ? 'Indicaciones del dia, aplicadas y canceladas incluidas'
            : `${pending.length} indicacion(es) pendiente(s)`
        }
        action={
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={showResolved}
              onChange={(event) => setShowResolved(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Ver lo resuelto hoy
          </label>
        }
      />

      <FormError message={error} />

      {tasksQuery.isLoading && <Spinner />}
      {tasksQuery.isError && <ErrorState message="No se pudieron cargar las tareas." />}

      {tasksQuery.data && tasks.length === 0 && (
        <Card className="p-6">
          <EmptyState
            message={
              showResolved
                ? 'Hoy no hubo tareas de enfermeria.'
                : 'No hay indicaciones pendientes. Todo al dia.'
            }
          />
        </Card>
      )}

      <div className="space-y-6">
        {Object.entries(byWard).map(([ward, wardTasks]) => (
          <Card key={ward} className="overflow-hidden">
            <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-3">
              <BedDouble className="h-4 w-4 text-teal-600" />
              <p className="text-sm font-bold text-slate-800">{ward}</p>
              <span className="text-xs text-slate-400">({wardTasks.length})</span>
            </div>
            <ul className="divide-y divide-slate-100">
              {wardTasks.map((task) => (
                <li key={task.id} className="flex flex-wrap items-start gap-4 px-5 py-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-teal-50">
                    <Syringe className="h-5 w-5 text-teal-600" />
                  </div>

                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-800">
                      {task.practice_name}
                      {Number(task.quantity) !== 1 && (
                        <span className="ml-2 text-xs font-medium text-slate-500">
                          x{Number(task.quantity)}
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-slate-500">
                      {task.patient_name}
                      {task.bed_code ? ` · cama ${task.bed_code}` : ' · sin cama'}
                      {task.room_code ? ` (hab. ${task.room_code})` : ''}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {task.practice_code} · indicada {formatDateTime(task.prescribed_at)}
                      {task.prescribed_by ? ` por ${task.prescribed_by}` : ''}
                    </p>
                    {task.indication && (
                      <p className="mt-1 text-xs italic text-slate-500">{task.indication}</p>
                    )}
                    {task.status !== 'REQUESTED' && (
                      <p className="mt-1 text-xs text-slate-400">
                        {task.performed_at
                          ? `Aplicada ${formatDateTime(task.performed_at)}` +
                            (task.performed_by ? ` por ${task.performed_by}` : '')
                          : task.cancelled_at
                            ? `Cancelada ${formatDateTime(task.cancelled_at)}`
                            : ''}
                        {task.notes ? ` · ${task.notes}` : ''}
                      </p>
                    )}
                  </div>

                  <div className="flex shrink-0 flex-col items-end gap-2">
                    <Badge
                      status={PRACTICE_ORDER_STATUS_LABELS[task.status]}
                      color={PRACTICE_ORDER_STATUS_COLORS[task.status]}
                    />
                    <Link
                      to={`/hospitalizations/${task.hospitalization_id}`}
                      className="flex items-center gap-1 text-xs font-medium text-teal-600 hover:text-teal-700"
                    >
                      <ClipboardList className="h-3.5 w-3.5" />
                      Ver internacion
                    </Link>
                    {task.status === 'REQUESTED' && (
                      <div className="flex gap-2">
                        <ActionButton
                          tone="success"
                          disabled={performMutation.isPending}
                          onClick={() => {
                            setError(null);
                            performMutation.mutate(task.id);
                          }}
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          Aplicada
                        </ActionButton>
                        <ActionButton
                          tone="danger"
                          onClick={() => {
                            setError(null);
                            setReason('');
                            setCancelling(task);
                          }}
                        >
                          <Ban className="h-4 w-4" />
                          Cancelar
                        </ActionButton>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      <Modal
        open={cancelling !== null}
        onClose={() => setCancelling(null)}
        title={cancelling ? `Cancelar ${cancelling.practice_name}` : ''}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (cancelling) cancelMutation.mutate({ taskId: cancelling.id, why: reason.trim() });
          }}
          className="space-y-4"
        >
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-xs text-slate-500">
            La tarea queda cancelada en la internacion de {cancelling?.patient_name}. El motivo
            es lo que va a leer quien la indico.
          </p>
          <Field label="Motivo">
            <input
              type="text"
              required
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="El paciente bajo a estudios"
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={() => setCancelling(null)}>
              Volver
            </ActionButton>
            <ActionButton tone="danger" type="submit" disabled={cancelMutation.isPending}>
              {cancelMutation.isPending ? 'Cancelando...' : 'Cancelar tarea'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
