import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDiagnoses } from '@/api/endpoints/diagnoses/diagnoses';
import type {
  DiagnosisCodeRead,
  DiagnosisRole,
  DiagnosisStage,
  HospitalizationDiagnosisRead,
  HospitalizationRead,
} from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import { useAuth } from '@/auth/AuthContext';
import { isPostDischarge } from './lock';
import DiagnosisPicker from '@/components/diagnoses/DiagnosisPicker';
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
  DIAGNOSIS_ROLE_COLORS,
  DIAGNOSIS_ROLE_LABELS,
  DIAGNOSIS_STAGE_LABELS,
} from '@/config/diagnosisLabels';
import { axiosInstance } from '@/api/custom-instance';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { BookMarked, Plus, Printer, Trash2 } from 'lucide-react';

const STAGES: DiagnosisStage[] = ['ADMISSION', 'DISCHARGE'];

export function DiagnosesCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getDiagnoses();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [stage, setStage] = useState<DiagnosisStage>('ADMISSION');
  const [picked, setPicked] = useState<DiagnosisCodeRead | null>(null);
  const [role, setRole] = useState<DiagnosisRole>('SECONDARY');
  const [notes, setNotes] = useState('');
  /** Quien lo indico: se exige, y se conserva entre diagnosticos porque suele ser el mismo. */
  const [diagnosedById, setDiagnosedById] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  const diagnosesQuery = useQuery({
    queryKey: ['hospitalization-diagnoses', hosp.id],
    queryFn: () =>
      api.listHospitalizationDiagnosesApiV1HospitalizationsHospitalizationIdDiagnosesGet(hosp.id),
  });

  const reset = () => {
    setPicked(null);
    setRole('SECONDARY');
    setNotes('');
  };

  const addMutation = useMutation({
    mutationFn: () =>
      api.addHospitalizationDiagnosisApiV1HospitalizationsHospitalizationIdDiagnosesPost(hosp.id, {
        code: picked!.code,
        role,
        stage,
        diagnosed_by_id: diagnosedById,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      queryClient.invalidateQueries({ queryKey: ['hospitalization-diagnoses', hosp.id] });
      setError(null);
      reset();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo asentar el diagnostico.')),
  });

  const removeMutation = useMutation({
    mutationFn: (entryId: string) =>
      api.removeHospitalizationDiagnosisApiV1HospitalizationsHospitalizationIdDiagnosesEntryIdDelete(
        hosp.id,
        entryId,
      ),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      queryClient.invalidateQueries({ queryKey: ['hospitalization-diagnoses', hosp.id] });
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo quitar el diagnostico.')),
  });

  /** El resumen de alta viaja con la sesion: se descarga y se abre desde memoria. */
  const printSummary = async () => {
    setError(null);
    setPrinting(true);
    try {
      const response = await axiosInstance.get(
        `/api/v1/hospitalizations/${hosp.id}/discharge-summary/pdf`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
      window.open(url, '_blank', 'noopener');
      // Se libera despues de que el navegador lo tomo.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (printError) {
      setError(apiErrorMessage(printError, 'No se pudo generar el resumen de alta.'));
    } finally {
      setPrinting(false);
    }
  };

  const entries = diagnosesQuery.data ?? [];
  // Despues del alta medica el diagnostico es lo que el medico firmo: solo lo corrige un admin.
  const canEdit = canManage && (!isPostDischarge(hosp.status) || user?.role === 'ADMIN');

  const byStage = (value: DiagnosisStage): HospitalizationDiagnosisRead[] =>
    entries.filter((entry) => entry.stage === value);

  return (
    <Card className="p-6">
      <SectionTitle icon={<BookMarked className="h-5 w-5 text-teal-600" />}>
        Diagnosticos CIE-10
      </SectionTitle>

      <div className="space-y-5">
        {STAGES.map((value) => {
          const list = byStage(value);
          return (
            <div key={value}>
              <p className="mb-2 text-sm font-semibold text-slate-700">
                {DIAGNOSIS_STAGE_LABELS[value]}
              </p>
              {list.length === 0 ? (
                <p className="text-sm text-slate-400">
                  {value === 'ADMISSION'
                    ? 'La admision no dejo diagnosticos codificados.'
                    : 'El alta medica todavia no asento el diagnostico definitivo.'}
                </p>
              ) : (
                <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
                  {list.map((entry) => (
                    <div
                      key={entry.id}
                      className="flex flex-wrap items-center justify-between gap-3 px-4 py-2"
                    >
                      <div>
                        <p className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold">
                            {entry.code}
                          </span>
                          {entry.description}
                        </p>
                        <p className="text-xs text-slate-500">
                          Indicado por{' '}
                          <span className="font-semibold text-slate-600">
                            {entry.diagnosed_by_name ?? 'profesional sin registrar'}
                          </span>
                        </p>
                        <p className="text-xs text-slate-400">
                          {formatDateTime(entry.diagnosed_at)}
                          {entry.recorded_by_user_name
                            ? ` · cargado por ${entry.recorded_by_user_name}`
                            : ''}
                          {entry.notes ? ` · ${entry.notes}` : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge
                          status={DIAGNOSIS_ROLE_LABELS[entry.role]}
                          color={DIAGNOSIS_ROLE_COLORS[entry.role]}
                        />
                        {canEdit && (
                          <button
                            type="button"
                            onClick={() => removeMutation.mutate(entry.id)}
                            disabled={removeMutation.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                            title="Quitar diagnostico"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {canEdit && (
        <div className="mt-5 space-y-3 rounded-lg bg-slate-50 p-4">
          <p className="text-sm font-semibold text-slate-700">Asentar un diagnostico</p>
          {picked ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-white px-3 py-2">
              <p className="text-sm text-slate-700">
                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold">
                  {picked.code}
                </span>{' '}
                {picked.description}
              </p>
              <ActionButton tone="neutral" onClick={() => setPicked(null)}>
                Cambiar
              </ActionButton>
            </div>
          ) : (
            <DiagnosisPicker onSelect={setPicked} />
          )}

          <Field label="Profesional que lo indica">
            <ProfessionalPicker
              value={diagnosedById}
              onSelect={setDiagnosedById}
              emptyLabel="Elegir profesional"
            />
          </Field>

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Momento">
              <select
                value={stage}
                onChange={(event) => setStage(event.target.value as DiagnosisStage)}
                className={inputClass}
              >
                {STAGES.map((value) => (
                  <option key={value} value={value}>
                    {DIAGNOSIS_STAGE_LABELS[value]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Rol">
              <select
                value={role}
                onChange={(event) => setRole(event.target.value as DiagnosisRole)}
                className={inputClass}
              >
                {Object.entries(DIAGNOSIS_ROLE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Notas">
              <input
                type="text"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                className={inputClass}
              />
            </Field>
          </div>

          <FormError message={error} />
          <div className="flex justify-end">
            <ActionButton
              tone="teal"
              disabled={!picked || !diagnosedById || addMutation.isPending}
              onClick={() => addMutation.mutate()}
            >
              <Plus className="h-4 w-4" />
              {addMutation.isPending ? 'Asentando...' : 'Asentar diagnostico'}
            </ActionButton>
          </div>
        </div>
      )}

      {!canEdit && <FormError message={error} />}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <p className="text-xs text-slate-400">
          El resumen de alta se arma con estos diagnosticos, las practicas realizadas y la
          medicacion indicada. Sin alta medica sale marcado como provisorio.
        </p>
        <ActionButton tone="primary" onClick={printSummary} disabled={printing}>
          <Printer className="h-4 w-4" />
          {printing ? 'Generando...' : 'Resumen de alta'}
        </ActionButton>
      </div>
    </Card>
  );
}

export default DiagnosesCard;
