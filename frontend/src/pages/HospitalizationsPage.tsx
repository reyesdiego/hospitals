import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { useAuth } from '@/auth/AuthContext';
import { HospitalizationStatusBadge } from '@/components/StatusBadges';
import { ActionButton, Card, EmptyState, ErrorState, PageHeader, Spinner } from '@/components/ui';
import { formatDateTime } from '@/utils/format';
import { ClipboardPlus, Plus } from 'lucide-react';

export default function HospitalizationsPage() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const api = getDefault();

  const canCreate = can('ADMISSION');

  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });
  const hospitalizationsQuery = useQuery({
    queryKey: ['hospitalizations'],
    queryFn: () => api.listHospitalizationsApiV1HospitalizationsGet(),
  });
  const admissionsQuery = useQuery({
    queryKey: ['admissions'],
    queryFn: () => api.listAdmissionsApiV1AdmissionsGet(),
  });

  const isLoading = patientsQuery.isLoading || hospitalizationsQuery.isLoading;
  const isError = patientsQuery.isError || hospitalizationsQuery.isError;

  const patients = patientsQuery.data ?? [];
  const hospitalizations = hospitalizationsQuery.data ?? [];
  const admissionByHospitalization = new Map(
    (admissionsQuery.data ?? [])
      .filter((admission) => admission.hospitalization_id)
      .map((admission) => [admission.hospitalization_id as string, admission]),
  );

  return (
    <div>
      <PageHeader
        title="Internaciones"
        subtitle="Toda internacion nace de una solicitud de admision"
        action={
          canCreate ? (
            <ActionButton
              tone="primary"
              onClick={() => navigate('/admissions')}
              className="px-4 py-2.5"
            >
              <Plus className="h-4 w-4" />
              Nueva admision
            </ActionButton>
          ) : undefined
        }
      />

      {isLoading && <Spinner />}
      {isError && <ErrorState message="No se pudieron cargar los datos." />}

      {!isLoading && !isError && (
        <>
          {hospitalizations.length === 0 ? (
            <Card className="p-6">
              <EmptyState message="No hay internaciones registradas. Registra una solicitud de admision para comenzar." />
            </Card>
          ) : (
            <div className="space-y-4">
              {hospitalizations.map((hospitalization) => {
                const patient = patients.find((item) => item.id === hospitalization.patient_id);
                const patientName = patient
                  ? `${patient.first_name} ${patient.last_name}`
                  : 'Paciente desconocido';
                const admission = admissionByHospitalization.get(hospitalization.id);

                return (
                  <Card
                    key={hospitalization.id}
                    className="cursor-pointer p-5 transition-all hover:border-teal-300 hover:shadow-md"
                    onClick={() => navigate(`/hospitalizations/${hospitalization.id}`)}
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex items-start gap-4">
                        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-teal-50">
                          <ClipboardPlus className="h-6 w-6 text-teal-600" />
                        </div>
                        <div>
                          <p className="text-base font-bold text-slate-800">{patientName}</p>
                          <p className="text-sm text-slate-500">
                            {hospitalization.admission_reason}
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-3">
                            <HospitalizationStatusBadge status={hospitalization.status} />
                            {hospitalization.admitted_at && (
                              <span className="text-xs text-slate-400">
                                Ingreso: {formatDateTime(hospitalization.admitted_at)}
                              </span>
                            )}
                            {admission && (
                              <span className="text-xs text-slate-400">
                                Admision #{admission.id.slice(0, 8)}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
