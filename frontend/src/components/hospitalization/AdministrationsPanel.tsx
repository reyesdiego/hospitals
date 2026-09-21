import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getTreatments } from '@/api/endpoints/treatments/treatments';
import type { AdministrationStatus, TreatmentRead } from '@/api/model';
import { ActionButton, Field, FormError, inputClass } from '@/components/ui';
import { MEDICATION_ROUTE_LABELS } from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, Check } from 'lucide-react';

/** Las tomas de una indicacion: lo que enfermeria le dio al paciente, o no le pudo dar. */
export default function AdministrationsPanel({
  hospitalizationId,
  treatment,
  canRecord,
}: {
  hospitalizationId: string;
  treatment: TreatmentRead;
  canRecord: boolean;
}) {
  const api = getTreatments();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AdministrationStatus>('GIVEN');
  const [dose, setDose] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const administrationsQuery = useQuery({
    queryKey: ['administrations', treatment.id],
    queryFn: () =>
      api.listAdministrationsApiV1HospitalizationsHospitalizationIdTreatmentsTreatmentIdAdministrationsGet(
        hospitalizationId,
        treatment.id,
      ),
    enabled: open,
  });

  const done = () => {
    queryClient.invalidateQueries({ queryKey: ['administrations', treatment.id] });
    queryClient.invalidateQueries({ queryKey: ['medication-round'] });
    setError(null);
  };

  const registerMutation = useMutation({
    mutationFn: () =>
      api.registerAdministrationApiV1HospitalizationsHospitalizationIdTreatmentsTreatmentIdAdministrationsPost(
        hospitalizationId,
        treatment.id,
        {
          status,
          dose: dose.trim() || null,
          omission_reason: reason.trim() || null,
        },
      ),
    onSuccess: () => {
      done();
      setDose('');
      setReason('');
      setStatus('GIVEN');
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar la toma.')),
  });

  const voidMutation = useMutation({
    mutationFn: (administrationId: string) =>
      api.voidAdministrationApiV1HospitalizationsHospitalizationIdTreatmentsTreatmentIdAdministrationsAdministrationIdVoidPost(
        hospitalizationId,
        treatment.id,
        administrationId,
        { reason: null },
      ),
    onSuccess: done,
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo anular la toma.')),
  });

  const administrations = administrationsQuery.data ?? [];

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="text-xs font-semibold text-teal-700 hover:underline"
      >
        {open ? 'Ocultar tomas' : 'Ver y registrar tomas'}
      </button>

      {open && (
        <div className="mt-2 rounded-lg bg-slate-50 p-3">
          {administrationsQuery.isLoading && (
            <p className="text-xs text-slate-400">Cargando tomas...</p>
          )}
          {!administrationsQuery.isLoading && administrations.length === 0 && (
            <p className="text-xs text-slate-400">Todavia no se registraron tomas.</p>
          )}
          {administrations.length > 0 && (
            <div className="mb-3 divide-y divide-slate-100 rounded-lg bg-white">
              {administrations.map((item) => {
                const isVoid = item.status === 'VOID';
                return (
                  <div
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5"
                  >
                    <div>
                      <p
                        className={`text-xs font-medium ${
                          isVoid ? 'text-slate-400 line-through' : 'text-slate-700'
                        }`}
                      >
                        {item.status === 'OMITTED' ? 'No se dio' : 'Dada'}
                        {item.dose ? ` · ${item.dose}` : ''}
                        {item.route ? ` · ${MEDICATION_ROUTE_LABELS[item.route]}` : ''}
                      </p>
                      <p className="text-xs text-slate-400">
                        {formatDateTime(item.administered_at)}
                        {item.recorded_by_user_name ? ` · ${item.recorded_by_user_name}` : ''}
                        {item.omission_reason ? ` · ${item.omission_reason}` : ''}
                      </p>
                    </div>
                    {canRecord && !isVoid && (
                      <button
                        type="button"
                        onClick={() => voidMutation.mutate(item.id)}
                        disabled={voidMutation.isPending}
                        className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
                        title="Anular toma"
                      >
                        <Ban className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {canRecord && treatment.status === 'ACTIVE' && (
            <div className="grid gap-2 sm:grid-cols-[130px_minmax(0,1fr)_auto]">
              <Field label="Toma">
                <select
                  value={status}
                  onChange={(event) =>
                    setStatus(event.target.value as AdministrationStatus)
                  }
                  className={inputClass}
                >
                  <option value="GIVEN">Dada</option>
                  <option value="OMITTED">No se dio</option>
                </select>
              </Field>
              <Field label={status === 'OMITTED' ? 'Motivo' : 'Dosis (vacia: la indicada)'}>
                <input
                  type="text"
                  value={status === 'OMITTED' ? reason : dose}
                  onChange={(event) =>
                    status === 'OMITTED'
                      ? setReason(event.target.value)
                      : setDose(event.target.value)
                  }
                  placeholder={
                    status === 'OMITTED' ? 'Paciente en ayunas...' : treatment.dose ?? ''
                  }
                  className={inputClass}
                />
              </Field>
              <div className="flex items-end">
                <ActionButton
                  tone="teal"
                  disabled={
                    registerMutation.isPending ||
                    (status === 'OMITTED' && reason.trim() === '')
                  }
                  onClick={() => registerMutation.mutate()}
                >
                  <Check className="h-4 w-4" />
                  Registrar
                </ActionButton>
              </div>
            </div>
          )}
          <FormError message={error} />
        </div>
      )}
    </div>
  );
}
