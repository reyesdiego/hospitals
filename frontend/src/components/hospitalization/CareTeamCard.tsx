import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getHospitalizationWorkflow } from '@/api/endpoints/hospitalization-workflow/hospitalization-workflow';
import type { CareTeamRole, HospitalizationRead } from '@/api/model';
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
import { CARE_TEAM_ROLE_LABELS } from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { UserMinus, UserPlus, Users } from 'lucide-react';

const OPEN_STATUSES = ['PENDING_BED', 'IN_PROGRESS', 'DISCHARGE_PLANNED'];

export function CareTeamCard({
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
  const [practitionerId, setPractitionerId] = useState('');
  const [role, setRole] = useState<CareTeamRole>('NURSE');
  const [error, setError] = useState<string | null>(null);

  const careTeamQuery = useQuery({
    queryKey: ['care-team', hosp.id],
    queryFn: () => api.getCareTeamApiV1HospitalizationsHospitalizationIdCareTeamGet(hosp.id),
    retry: false,
  });
  const professionalsQuery = useQuery({
    queryKey: ['professionals'],
    queryFn: () => defaultApi.listProfessionalsApiV1ProfessionalsGet(),
  });

  const addMutation = useMutation({
    mutationFn: () =>
      api.addCareTeamMemberApiV1HospitalizationsHospitalizationIdCareTeamMembersPost(hosp.id, {
        practitioner_id: practitionerId,
        role,
      }),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setOpen(false);
      setPractitionerId('');
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo agregar al integrante.')),
  });

  const endMutation = useMutation({
    mutationFn: (memberId: string) =>
      api.endCareTeamMemberApiV1HospitalizationsHospitalizationIdCareTeamMembersMemberIdEndPost(
        hosp.id,
        memberId,
      ),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo finalizar la participacion.')),
  });

  const members = careTeamQuery.data?.members ?? [];
  const professionalsById = new Map(
    (professionalsQuery.data ?? []).map((professional) => [professional.id, professional]),
  );
  const activeMembers = members.filter((member) => member.ended_at === null);
  const pastMembers = members.filter((member) => member.ended_at !== null);
  const practitionerName = (id: string) => {
    const professional = professionalsById.get(id);
    return professional
      ? `${professional.last_name}, ${professional.first_name}`
      : `Profesional ${id.slice(0, 8)}`;
  };

  return (
    <Card className="p-6">
      <SectionTitle icon={<Users className="h-5 w-5 text-teal-600" />}>
        Equipo asistencial
      </SectionTitle>

      <div className="space-y-4">
        {activeMembers.length === 0 ? (
          <p className="text-sm text-slate-400">Sin integrantes activos.</p>
        ) : (
          <div className="space-y-2">
            {activeMembers.map((member) => (
              <div
                key={member.id}
                className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-4 py-3"
              >
                <div>
                  <p className="text-sm font-semibold text-slate-700">
                    {practitionerName(member.practitioner_id)}
                  </p>
                  <p className="text-xs text-slate-500">
                    {CARE_TEAM_ROLE_LABELS[member.role]} · desde{' '}
                    {formatDateTime(member.started_at)}
                  </p>
                </div>
                {canManage && OPEN_STATUSES.includes(hosp.status) && (
                  <ActionButton
                    tone="danger"
                    onClick={() => endMutation.mutate(member.id)}
                    disabled={endMutation.isPending}
                  >
                    <UserMinus className="h-4 w-4" />
                    Finalizar
                  </ActionButton>
                )}
              </div>
            ))}
          </div>
        )}

        <FormError message={error} />

        {canManage && OPEN_STATUSES.includes(hosp.status) && (
          <ActionButton tone="teal" onClick={() => setOpen(true)}>
            <UserPlus className="h-4 w-4" />
            Agregar integrante
          </ActionButton>
        )}

        {pastMembers.length > 0 && (
          <div className="rounded-lg border border-slate-100">
            <div className="border-b border-slate-100 px-4 py-3">
              <p className="text-sm font-semibold text-slate-700">Participaciones finalizadas</p>
            </div>
            <div className="divide-y divide-slate-100">
              {pastMembers.map((member) => (
                <div key={member.id} className="px-4 py-3">
                  <p className="text-sm text-slate-700">
                    {practitionerName(member.practitioner_id)}
                  </p>
                  <p className="text-xs text-slate-400">
                    {CARE_TEAM_ROLE_LABELS[member.role]} · {formatDateTime(member.started_at)} →{' '}
                    {formatDateTime(member.ended_at)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Agregar integrante">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (practitionerId) addMutation.mutate();
          }}
        >
          <Field label="Profesional">
            <select
              required
              value={practitionerId}
              onChange={(e) => setPractitionerId(e.target.value)}
              className={inputClass}
            >
              <option value="">Selecciona un profesional...</option>
              {(professionalsQuery.data ?? []).map((professional) => (
                <option key={professional.id} value={professional.id}>
                  {professional.last_name}, {professional.first_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Rol">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as CareTeamRole)}
              className={inputClass}
            >
              {Object.entries(CARE_TEAM_ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="primary"
              type="submit"
              disabled={!practitionerId || addMutation.isPending}
            >
              {addMutation.isPending ? 'Agregando...' : 'Agregar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

export default CareTeamCard;
