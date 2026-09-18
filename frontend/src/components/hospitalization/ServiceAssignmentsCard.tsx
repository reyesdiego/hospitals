import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getHospitalizationWorkflow } from '@/api/endpoints/hospitalization-workflow/hospitalization-workflow';
import type { HospitalizationRead } from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Card,
  Field,
  FormError,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Repeat, Stethoscope } from 'lucide-react';

const OPEN_STATUSES = ['PENDING_BED', 'IN_PROGRESS', 'DISCHARGE_PLANNED'];

export function ServiceAssignmentsCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getHospitalizationWorkflow();
  const defaultApi = getDefault();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [serviceId, setServiceId] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const assignmentsQuery = useQuery({
    queryKey: ['service-assignments', hosp.id],
    queryFn: () =>
      api.listServiceAssignmentsApiV1HospitalizationsHospitalizationIdServiceAssignmentsGet(hosp.id),
  });
  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => defaultApi.listServicesApiV1ServicesGet(),
  });

  const assignMutation = useMutation({
    mutationFn: () =>
      api.assignServiceApiV1HospitalizationsHospitalizationIdServiceAssignmentsPost(hosp.id, {
        service_id: serviceId,
        reason: reason || null,
      }),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setOpen(false);
      setServiceId('');
      setReason('');
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo cambiar el servicio responsable.')),
  });

  const assignments = assignmentsQuery.data ?? [];
  const servicesById = new Map((servicesQuery.data ?? []).map((service) => [service.id, service]));
  const current = assignments.find((assignment) => assignment.ended_at === null);
  const serviceName = (id: string) => servicesById.get(id)?.name ?? `Servicio ${id.slice(0, 8)}`;

  return (
    <Card className="p-6">
      <SectionTitle icon={<Stethoscope className="h-5 w-5 text-teal-600" />}>
        Servicio responsable
      </SectionTitle>

      <div className="space-y-4">
        <div className="rounded-lg bg-slate-50 px-4 py-3">
          {current ? (
            <>
              <p className="text-sm font-semibold text-slate-700">
                {serviceName(current.service_id)}
              </p>
              <p className="text-xs text-slate-500">
                Desde {formatDateTime(current.started_at)}
                {current.reason ? ` · ${current.reason}` : ''}
              </p>
            </>
          ) : (
            <p className="text-sm text-slate-500">Sin servicio responsable activo.</p>
          )}
        </div>

        <FormError message={error} />

        {canManage && OPEN_STATUSES.includes(hosp.status) && (
          <ActionButton tone="teal" onClick={() => setOpen(true)}>
            <Repeat className="h-4 w-4" />
            Cambiar servicio
          </ActionButton>
        )}

        {assignments.length > 1 && (
          <div className="rounded-lg border border-slate-100">
            <div className="border-b border-slate-100 px-4 py-3">
              <p className="text-sm font-semibold text-slate-700">Historial</p>
            </div>
            <div className="divide-y divide-slate-100">
              {assignments.map((assignment) => (
                <div key={assignment.id} className="px-4 py-3">
                  <p className="text-sm text-slate-700">{serviceName(assignment.service_id)}</p>
                  <p className="text-xs text-slate-400">
                    {formatDateTime(assignment.started_at)} →{' '}
                    {formatDateTime(assignment.ended_at) ?? 'Actualidad'}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Cambiar servicio responsable">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (serviceId) assignMutation.mutate();
          }}
        >
          <p className="text-sm text-slate-500">
            La asignacion anterior se cierra y queda en el historial.
          </p>
          <Field label="Nuevo servicio">
            <select
              required
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
              className={inputClass}
            >
              <option value="">Selecciona un servicio...</option>
              {(servicesQuery.data ?? [])
                .filter((service) => service.id !== current?.service_id)
                .map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Motivo">
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Pase a terapia intensiva"
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="primary"
              type="submit"
              disabled={!serviceId || assignMutation.isPending}
            >
              {assignMutation.isPending ? 'Guardando...' : 'Asignar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

export default ServiceAssignmentsCard;
