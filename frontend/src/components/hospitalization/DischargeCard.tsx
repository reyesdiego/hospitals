import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getHospitalizationWorkflow } from '@/api/endpoints/hospitalization-workflow/hospitalization-workflow';
import type {
  DiagnosisRole,
  DischargeDestination,
  DischargePlanCreate,
  DischargeType,
  HospitalizationRead,
} from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import Modal from '@/components/Modal';
import DiagnosisPicker from '@/components/diagnoses/DiagnosisPicker';
import ProfessionalPicker from '@/components/professionals/ProfessionalPicker';
import {
  ActionButton,
  Card,
  Field,
  FormError,
  InfoRow,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import {
  DISCHARGE_DESTINATION_LABELS,
  DISCHARGE_PLAN_STATUS_LABELS,
  DISCHARGE_TYPE_LABELS,
} from '@/config/workflowLabels';
import { DIAGNOSIS_ROLE_LABELS } from '@/config/diagnosisLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDate, formatDateTime } from '@/utils/format';
import { ClipboardCheck, DoorOpen, FileCheck2, Stethoscope } from 'lucide-react';

const CLINICALLY_ACTIVE = ['IN_PROGRESS', 'DISCHARGE_PLANNED'];

const emptyPlan: DischargePlanCreate = {
  planned_date: null,
  destination: 'HOME',
  requires_transport: false,
  requires_home_care: false,
  status: 'PLANNED',
  created_by: null,
  notes: null,
};

export function DischargeCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getHospitalizationWorkflow();
  const queryClient = useQueryClient();
  const [planOpen, setPlanOpen] = useState(false);
  const [dischargeOpen, setDischargeOpen] = useState(false);
  const [departureOpen, setDepartureOpen] = useState(false);
  const [administrativeOpen, setAdministrativeOpen] = useState(false);
  const [plan, setPlan] = useState<DischargePlanCreate>(emptyPlan);
  const [dischargeType, setDischargeType] = useState<DischargeType>('MEDICAL');
  const [dischargeReason, setDischargeReason] = useState('');
  const [dischargeDestination, setDischargeDestination] = useState<DischargeDestination | ''>('');
  const [practitionerId, setPractitionerId] = useState('');
  const [instructions, setInstructions] = useState('');
  const [releasedBy, setReleasedBy] = useState('');
  const [departureNotes, setDepartureNotes] = useState('');
  const [administrativeNotes, setAdministrativeNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  /** Diagnosticos de egreso: los que el medico firma con el alta. El primero es el principal. */
  const [dischargeDiagnoses, setDischargeDiagnoses] = useState<
    { code: string; description: string; role: DiagnosisRole }[]
  >([]);

  const plansQuery = useQuery({
    queryKey: ['discharge-plans', hosp.id],
    queryFn: () => api.listDischargePlansApiV1HospitalizationsHospitalizationIdDischargePlansGet(hosp.id),
  });
  const dischargeQuery = useQuery({
    queryKey: ['discharge', hosp.id],
    queryFn: () => api.getDischargeApiV1HospitalizationsHospitalizationIdDischargeGet(hosp.id),
    enabled: Boolean(hosp.clinically_discharged_at),
    retry: false,
  });

  const done = () => {
    invalidateHospitalization(queryClient, hosp.id);
    setError(null);
  };

  const planMutation = useMutation({
    mutationFn: () =>
      api.planDischargeApiV1HospitalizationsHospitalizationIdDischargePlansPost(hosp.id, plan),
    onSuccess: () => {
      done();
      setPlanOpen(false);
      setPlan(emptyPlan);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo planificar el alta.')),
  });

  const clinicalMutation = useMutation({
    mutationFn: () =>
      api.clinicalDischargeApiV1HospitalizationsHospitalizationIdClinicalDischargePost(hosp.id, {
        discharge_type: dischargeType,
        discharge_reason: dischargeReason || null,
        destination: dischargeDestination || null,
        ordered_by_practitioner_id: practitionerId || null,
        instructions: instructions || null,
        diagnoses: dischargeDiagnoses.map(({ code, role }) => ({
          code,
          role,
          stage: 'DISCHARGE' as const,
        })),
      }),
    onSuccess: () => {
      done();
      setDischargeOpen(false);
      setDischargeDiagnoses([]);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar el alta clinica.')),
  });

  const departureMutation = useMutation({
    mutationFn: () =>
      api.physicalDepartureApiV1HospitalizationsHospitalizationIdPhysicalDeparturePost(hosp.id, {
        released_by: releasedBy || null,
        notes: departureNotes || null,
      }),
    onSuccess: () => {
      done();
      setDepartureOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar la salida fisica.')),
  });

  const administrativeMutation = useMutation({
    mutationFn: () =>
      api.administrativeDischargeApiV1HospitalizationsHospitalizationIdAdministrativeDischargePost(
        hosp.id,
        { notes: administrativeNotes || null },
      ),
    onSuccess: () => {
      done();
      setAdministrativeOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar el alta administrativa.')),
  });

  const plans = plansQuery.data ?? [];
  const activePlan = plans.find((item) => item.status === 'PLANNED' || item.status === 'CONFIRMED');
  const discharge = dischargeQuery.data;
  const busy =
    planMutation.isPending ||
    clinicalMutation.isPending ||
    departureMutation.isPending ||
    administrativeMutation.isPending;

  const canPlan = canManage && CLINICALLY_ACTIVE.includes(hosp.status) && !activePlan;
  const canDischarge = canManage && CLINICALLY_ACTIVE.includes(hosp.status);
  const canDepart =
    canManage && Boolean(hosp.clinically_discharged_at) && !hosp.physically_departed_at;
  const canCloseAdministratively =
    canManage &&
    Boolean(hosp.physically_departed_at) &&
    !hosp.administratively_discharged_at;

  return (
    <Card className="p-6">
      <SectionTitle icon={<ClipboardCheck className="h-5 w-5 text-teal-600" />}>
        Alta y egreso
      </SectionTitle>

      <div className="space-y-4">
        {hosp.clinically_discharged_at && !hosp.physically_departed_at && (
          <p className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
            El alta clinica ya fue registrada. La cama sigue ocupada hasta que se registre la
            salida fisica del paciente.
          </p>
        )}

        {activePlan ? (
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
            <p className="text-sm font-semibold text-indigo-800">
              Alta planificada · {DISCHARGE_PLAN_STATUS_LABELS[activePlan.status]}
            </p>
            <p className="mt-1 text-xs text-indigo-700">
              {formatDate(activePlan.planned_date) ?? 'Sin fecha'} ·{' '}
              {DISCHARGE_DESTINATION_LABELS[activePlan.destination]}
              {activePlan.requires_transport ? ' · requiere traslado' : ''}
              {activePlan.requires_home_care ? ' · requiere internacion domiciliaria' : ''}
            </p>
            {activePlan.notes && (
              <p className="mt-1 text-xs text-indigo-700">{activePlan.notes}</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-slate-400">Sin plan de alta activo.</p>
        )}

        {discharge && (
          <div className="space-y-2">
            <InfoRow
              label="Tipo de alta"
              value={DISCHARGE_TYPE_LABELS[discharge.discharge_type]}
            />
            <InfoRow
              label="Alta clinica efectiva"
              value={formatDateTime(discharge.effective_at) ?? '—'}
            />
            {discharge.discharge_reason && (
              <InfoRow label="Motivo" value={discharge.discharge_reason} />
            )}
            {discharge.instructions && (
              <InfoRow label="Indicaciones" value={discharge.instructions} />
            )}
          </div>
        )}

        <FormError message={error} />

        <div className="flex flex-wrap gap-2">
          {canPlan && (
            <ActionButton tone="teal" onClick={() => setPlanOpen(true)} disabled={busy}>
              <ClipboardCheck className="h-4 w-4" />
              Planificar alta
            </ActionButton>
          )}
          {canDischarge && (
            <ActionButton tone="primary" onClick={() => setDischargeOpen(true)} disabled={busy}>
              <Stethoscope className="h-4 w-4" />
              Registrar alta clinica
            </ActionButton>
          )}
          {canDepart && (
            <ActionButton tone="warning" onClick={() => setDepartureOpen(true)} disabled={busy}>
              <DoorOpen className="h-4 w-4" />
              Registrar salida fisica
            </ActionButton>
          )}
          {canCloseAdministratively && (
            <ActionButton
              tone="success"
              onClick={() => setAdministrativeOpen(true)}
              disabled={busy}
            >
              <FileCheck2 className="h-4 w-4" />
              Alta administrativa
            </ActionButton>
          )}
        </div>

        {plans.length > 0 && (
          <div className="rounded-lg border border-slate-100">
            <div className="border-b border-slate-100 px-4 py-3">
              <p className="text-sm font-semibold text-slate-700">Planes de alta</p>
            </div>
            <div className="divide-y divide-slate-100">
              {plans.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div>
                    <p className="text-sm text-slate-700">
                      {DISCHARGE_DESTINATION_LABELS[item.destination]} ·{' '}
                      {formatDate(item.planned_date) ?? 'sin fecha'}
                    </p>
                    <p className="text-xs text-slate-400">
                      Registrado {formatDateTime(item.created_at)}
                      {item.created_by ? ` por ${item.created_by}` : ''}
                    </p>
                  </div>
                  <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-500">
                    {DISCHARGE_PLAN_STATUS_LABELS[item.status]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Modal open={planOpen} onClose={() => setPlanOpen(false)} title="Planificar alta">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            planMutation.mutate();
          }}
        >
          <p className="text-sm text-slate-500">
            Planificar el alta no libera la cama ni finaliza la internacion.
          </p>
          <Field label="Fecha prevista">
            <input
              type="date"
              value={plan.planned_date ?? ''}
              onChange={(e) => setPlan({ ...plan, planned_date: e.target.value || null })}
              className={inputClass}
            />
          </Field>
          <Field label="Destino">
            <select
              value={plan.destination ?? 'HOME'}
              onChange={(e) =>
                setPlan({ ...plan, destination: e.target.value as DischargeDestination })
              }
              className={inputClass}
            >
              {Object.entries(DISCHARGE_DESTINATION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={plan.requires_transport ?? false}
                onChange={(e) => setPlan({ ...plan, requires_transport: e.target.checked })}
              />
              Requiere traslado
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={plan.requires_home_care ?? false}
                onChange={(e) => setPlan({ ...plan, requires_home_care: e.target.checked })}
              />
              Requiere internacion domiciliaria
            </label>
          </div>
          <Field label="Notas">
            <textarea
              rows={3}
              value={plan.notes ?? ''}
              onChange={(e) => setPlan({ ...plan, notes: e.target.value || null })}
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setPlanOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={busy}>
              {planMutation.isPending ? 'Guardando...' : 'Guardar plan'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={dischargeOpen}
        onClose={() => setDischargeOpen(false)}
        title="Registrar alta clinica"
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            clinicalMutation.mutate();
          }}
        >
          <p className="text-sm text-slate-500">
            La cama permanece ocupada: la salida fisica del paciente se registra por separado.
          </p>
          <Field label="Tipo de alta">
            <select
              value={dischargeType}
              onChange={(e) => setDischargeType(e.target.value as DischargeType)}
              className={inputClass}
            >
              {Object.entries(DISCHARGE_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Medico que indica el alta">
            <ProfessionalPicker value={practitionerId} onSelect={setPractitionerId} />
          </Field>
          <Field label="Destino">
            <select
              value={dischargeDestination}
              onChange={(e) => setDischargeDestination(e.target.value as DischargeDestination)}
              className={inputClass}
            >
              <option value="">Sin especificar</option>
              {Object.entries(DISCHARGE_DESTINATION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Motivo">
            <input
              type="text"
              value={dischargeReason}
              onChange={(e) => setDischargeReason(e.target.value)}
              placeholder="Evolucion favorable"
              className={inputClass}
            />
          </Field>
          <Field label="Indicaciones al paciente">
            <textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              className={inputClass}
            />
          </Field>
          <div className="rounded-lg bg-slate-50 p-3">
            <p className="mb-2 text-sm font-semibold text-slate-700">
              Diagnosticos de egreso (CIE-10)
            </p>
            <p className="mb-2 text-xs text-slate-500">
              Los de ingreso quedan como estan: la diferencia entre lo que se sospecho y lo
              que resulto es parte de la historia. Los de egreso quedan indicados por el medico
              que indica el alta.
            </p>
            {dischargeDiagnoses.length > 0 && !practitionerId && (
              <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                Elegi el medico que indica el alta: es quien firma estos diagnosticos.
              </p>
            )}
            <DiagnosisPicker
              onSelect={(code) =>
                setDischargeDiagnoses((current) =>
                  current.some((item) => item.code === code.code)
                    ? current
                    : [
                        ...current,
                        {
                          code: code.code,
                          description: code.description,
                          role: current.length === 0 ? 'PRINCIPAL' : 'SECONDARY',
                        },
                      ],
                )
              }
            />
            {dischargeDiagnoses.length > 0 && (
              <div className="mt-2 divide-y divide-slate-100 rounded-lg bg-white">
                {dischargeDiagnoses.map((item) => (
                  <div
                    key={item.code}
                    className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
                  >
                    <p className="text-sm text-slate-700">
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold">
                        {item.code}
                      </span>{' '}
                      {item.description}
                    </p>
                    <div className="flex items-center gap-2">
                      <select
                        value={item.role}
                        onChange={(e) =>
                          setDischargeDiagnoses((current) =>
                            current.map((entry) =>
                              entry.code === item.code
                                ? { ...entry, role: e.target.value as DiagnosisRole }
                                : entry,
                            ),
                          )
                        }
                        className="rounded-lg border border-slate-200 px-2 py-1 text-xs outline-none focus:border-teal-500"
                      >
                        {Object.entries(DIAGNOSIS_ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() =>
                          setDischargeDiagnoses((current) =>
                            current.filter((entry) => entry.code !== item.code),
                          )
                        }
                        className="rounded-lg px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50"
                      >
                        Quitar
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setDischargeOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="primary"
              type="submit"
              disabled={busy || (dischargeDiagnoses.length > 0 && !practitionerId)}
            >
              {clinicalMutation.isPending ? 'Registrando...' : 'Registrar alta clinica'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={departureOpen}
        onClose={() => setDepartureOpen(false)}
        title="Registrar salida fisica"
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            departureMutation.mutate();
          }}
        >
          <p className="text-sm text-slate-500">
            Al registrar la salida se finaliza la ocupacion y la cama pasa a pendiente de limpieza.
          </p>
          <Field label="Registrado por">
            <input
              type="text"
              value={releasedBy}
              onChange={(e) => setReleasedBy(e.target.value)}
              placeholder="Enfermeria"
              className={inputClass}
            />
          </Field>
          <Field label="Notas">
            <textarea
              rows={3}
              value={departureNotes}
              onChange={(e) => setDepartureNotes(e.target.value)}
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setDepartureOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton tone="warning" type="submit" disabled={busy}>
              {departureMutation.isPending ? 'Registrando...' : 'Registrar salida'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={administrativeOpen}
        onClose={() => setAdministrativeOpen(false)}
        title="Alta administrativa"
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            administrativeMutation.mutate();
          }}
        >
          <p className="text-sm text-slate-500">
            Cierra el servicio responsable y el equipo asistencial, y entrega la cuenta a
            facturacion. El cierre financiero es un paso posterior e independiente.
          </p>
          <Field label="Notas administrativas">
            <textarea
              rows={3}
              value={administrativeNotes}
              onChange={(e) => setAdministrativeNotes(e.target.value)}
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setAdministrativeOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton tone="success" type="submit" disabled={busy}>
              {administrativeMutation.isPending ? 'Registrando...' : 'Registrar alta administrativa'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

export default DischargeCard;
