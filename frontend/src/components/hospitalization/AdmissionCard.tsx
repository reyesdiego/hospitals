import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getAuthorizations } from '@/api/endpoints/authorizations/authorizations';
import { getDefault } from '@/api/endpoints/default/default';
import type { HospitalizationRead } from '@/api/model';
import { ActionButton, Card, EmptyState, InfoRow, SectionTitle } from '@/components/ui';
import {
  ADMISSION_ORIGIN_LABELS,
  ADMISSION_STATUS_COLORS,
  ADMISSION_STATUS_LABELS,
  ADMISSION_TYPE_LABELS,
  AUTHORIZATION_STATE_COLORS,
  AUTHORIZATION_STATE_LABELS,
  AUTHORIZATION_TYPE_LABELS,
  CONSENT_TYPE_LABELS,
  COVERAGE_AUTHORIZATION_LABELS,
} from '@/config/workflowLabels';
import { formatDateTime } from '@/utils/format';
import { ClipboardList, ExternalLink } from 'lucide-react';

/**
 * The admission request that justifies this stay. It is a separate entity: the request
 * exists before the hospitalization and keeps its own status, coverage and consents.
 */
export function AdmissionCard({ hosp }: { hosp: HospitalizationRead }) {
  const navigate = useNavigate();
  const api = getDefault();
  const authorizationsApi = getAuthorizations();

  const admissionsQuery = useQuery({
    queryKey: ['admissions', hosp.id],
    queryFn: () => api.listAdmissionsApiV1AdmissionsGet({ hospitalization_id: hosp.id }),
  });
  const authorizationsQuery = useQuery({
    queryKey: ['authorizations', hosp.id],
    queryFn: () =>
      authorizationsApi.listHospitalizationAuthorizationsApiV1HospitalizationsHospitalizationIdAuthorizationsGet(
        hosp.id,
      ),
  });
  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => api.listServicesApiV1ServicesGet(),
  });

  const admission = (admissionsQuery.data ?? [])[0];
  const authorizations = authorizationsQuery.data ?? [];
  const requestingService = admission?.requesting_service_id
    ? (servicesQuery.data ?? []).find((service) => service.id === admission.requesting_service_id)
    : undefined;

  if (!admission) {
    return (
      <Card className="p-6">
        <SectionTitle icon={<ClipboardList className="h-5 w-5 text-teal-600" />}>
          Solicitud de admision
        </SectionTitle>
        <EmptyState
          message={
            admissionsQuery.isLoading
              ? 'Cargando la solicitud de admision...'
              : 'Esta internacion no tiene una solicitud de admision asociada.'
          }
        />
      </Card>
    );
  }

  return (
    <Card className="p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SectionTitle icon={<ClipboardList className="h-5 w-5 text-teal-600" />}>
          Solicitud de admision
        </SectionTitle>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            ADMISSION_STATUS_COLORS[admission.status]
          }`}
        >
          {ADMISSION_STATUS_LABELS[admission.status]}
        </span>
      </div>

      <div className="space-y-3">
        <InfoRow label="Solicitud" value={`#${admission.id.slice(0, 8)}`} />
        <InfoRow label="Origen" value={ADMISSION_ORIGIN_LABELS[admission.origin]} />
        <InfoRow label="Tipo" value={ADMISSION_TYPE_LABELS[admission.admission_type]} />
        <InfoRow
          label="Solicitada"
          value={formatDateTime(admission.requested_at ?? admission.created_at) ?? '—'}
        />
        {admission.episode && (
          <InfoRow label="Episodio" value={admission.episode.episode_number} />
        )}
        {requestingService && (
          <InfoRow label="Servicio solicitante" value={requestingService.name} />
        )}
        <InfoRow label="Medico responsable" value={admission.responsible_physician} />
        {admission.presumptive_diagnosis && (
          <InfoRow label="Diagnostico presuntivo" value={admission.presumptive_diagnosis} />
        )}
        <InfoRow
          label="Contacto responsable"
          value={
            <>
              {admission.responsible_contact_name ?? 'Pendiente: se toma cuando llega el paciente'}
              <span className="block text-xs font-normal text-slate-400">
                {admission.responsible_contact_phone ?? ''}
                {admission.responsible_contact_relationship
                  ? ` · ${admission.responsible_contact_relationship}`
                  : ''}
              </span>
            </>
          }
        />

        <div className="rounded-lg border border-slate-100">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-700">Cobertura</p>
          </div>
          {admission.coverage ? (
            <div className="px-4 py-3">
              <p className="text-sm font-semibold text-slate-700">
                {admission.coverage.payer_name}
                {admission.coverage.plan_name ? ` · ${admission.coverage.plan_name}` : ''}
              </p>
              <p className="text-xs text-slate-400">
                {admission.coverage.member_number
                  ? `Afiliado ${admission.coverage.member_number} · `
                  : ''}
                {COVERAGE_AUTHORIZATION_LABELS[admission.authorization_status]}
                {admission.authorization_number ? ` (${admission.authorization_number})` : ''}
              </p>
            </div>
          ) : (
            <p className="px-4 py-3 text-sm text-slate-400">
              Sin cobertura registrada ·{' '}
              {COVERAGE_AUTHORIZATION_LABELS[admission.authorization_status]}
            </p>
          )}
        </div>

        <div className="rounded-lg border border-slate-100">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-700">Autorizaciones</p>
          </div>
          {authorizations.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-400">Sin autorizaciones registradas.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {authorizations.map((authorization) => (
                <div
                  key={authorization.id}
                  className="flex items-center justify-between gap-3 px-4 py-3"
                >
                  <div>
                    <p className="text-sm text-slate-700">
                      {AUTHORIZATION_TYPE_LABELS[authorization.authorization_type]}
                      {authorization.authorization_number
                        ? ` · ${authorization.authorization_number}`
                        : ''}
                    </p>
                    <p className="text-xs text-slate-400">
                      Solicitada {formatDateTime(authorization.requested_at)}
                      {authorization.resolved_at
                        ? ` · resuelta ${formatDateTime(authorization.resolved_at)}`
                        : ''}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${
                      AUTHORIZATION_STATE_COLORS[authorization.status]
                    }`}
                  >
                    {AUTHORIZATION_STATE_LABELS[authorization.status]}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {admission.consents && admission.consents.length > 0 && (
          <div className="rounded-lg border border-slate-100">
            <div className="border-b border-slate-100 px-4 py-3">
              <p className="text-sm font-semibold text-slate-700">Consentimientos</p>
            </div>
            <div className="divide-y divide-slate-100">
              {admission.consents.map((consent) => (
                <div key={consent.id} className="px-4 py-3">
                  <p className="text-sm text-slate-700">
                    {CONSENT_TYPE_LABELS[consent.consent_type]}
                  </p>
                  <p className="text-xs text-slate-400">
                    {consent.signed_by} · {formatDateTime(consent.signed_at) ?? 'sin firma'}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {admission.notes && <InfoRow label="Notas" value={admission.notes} />}

        <ActionButton tone="neutral" onClick={() => navigate('/admissions')}>
          <ExternalLink className="h-4 w-4" />
          Ver en el panel de admision
        </ActionButton>
      </div>
    </Card>
  );
}

export default AdmissionCard;
