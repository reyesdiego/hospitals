import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getHospitalizationWorkflow } from '@/api/endpoints/hospitalization-workflow/hospitalization-workflow';
import { useAuth } from '@/auth/AuthContext';
import AccountCard from '@/components/hospitalization/AccountCard';
import AdmissionCard from '@/components/hospitalization/AdmissionCard';
import { isPostDischarge } from '@/components/hospitalization/lock';
import BedManagementCard from '@/components/hospitalization/BedManagementCard';
import CareTeamCard from '@/components/hospitalization/CareTeamCard';
import DiagnosesCard from '@/components/hospitalization/DiagnosesCard';
import DischargeCard from '@/components/hospitalization/DischargeCard';
import DischargePrescriptionsCard from '@/components/hospitalization/DischargePrescriptionsCard';
import EventsCard from '@/components/hospitalization/EventsCard';
import LifecycleCard from '@/components/hospitalization/LifecycleCard';
import PracticesCard from '@/components/hospitalization/PracticesCard';
import ServiceAssignmentsCard from '@/components/hospitalization/ServiceAssignmentsCard';
import { Card, ErrorState, InfoRow, PageHeader, SectionTitle, Spinner } from '@/components/ui';
import { formatDate } from '@/utils/format';
import { ArrowLeft, FileText, Lock, User } from 'lucide-react';

function ageAtDate(birthDate: string | null | undefined, referenceDate: string | null | undefined) {
  if (!birthDate || !referenceDate) return null;
  const birth = new Date(`${birthDate}T00:00:00`);
  const reference = new Date(referenceDate);
  let age = reference.getFullYear() - birth.getFullYear();
  const monthDelta = reference.getMonth() - birth.getMonth();
  if (monthDelta < 0 || (monthDelta === 0 && reference.getDate() < birth.getDate())) {
    age -= 1;
  }
  return age >= 0 ? age : null;
}

export default function HospitalizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, can } = useAuth();
  const api = getDefault();
  const workflowApi = getHospitalizationWorkflow();

  const canManage = can('HOSPITALIZATION');
  const isAdmin = user?.role === 'ADMIN';

  const hospitalizationQuery = useQuery({
    queryKey: ['hospitalization', id],
    queryFn: () =>
      workflowApi.getHospitalizationApiV1HospitalizationsHospitalizationIdGet(id ?? ''),
    enabled: Boolean(id),
    retry: false,
  });
  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });

  const hosp = hospitalizationQuery.data;

  if (hospitalizationQuery.isLoading || patientsQuery.isLoading) {
    return <Spinner />;
  }

  if (!hosp) {
    return (
      <div>
        <button
          onClick={() => navigate('/hospitalizations')}
          className="mb-4 flex items-center gap-2 text-sm font-medium text-teal-600 hover:text-teal-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver
        </button>
        <ErrorState message="No se encontro la hospitalizacion solicitada." />
      </div>
    );
  }

  const patient = patientsQuery.data?.find((item) => item.id === hosp.patient_id);
  const patientName = patient
    ? `${patient.first_name} ${patient.last_name}`
    : 'Paciente desconocido';
  const patientAgeAtAdmission = ageAtDate(patient?.birth_date, hosp.admitted_at);

  return (
    <div>
      <button
        onClick={() => navigate('/hospitalizations')}
        className="mb-4 flex items-center gap-2 text-sm font-medium text-teal-600 transition-colors hover:text-teal-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Volver a hospitalizaciones
      </button>

      <PageHeader title={patientName} subtitle={`Internacion #${hosp.id.slice(0, 8)}`} />

      {isPostDischarge(hosp.status) && (
        <Card className="mb-6 flex items-start gap-3 border-amber-200 bg-amber-50 px-5 py-4">
          <Lock className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div>
            <p className="text-sm font-semibold text-amber-800">
              Internacion con alta medica: cerrada a modificaciones
            </p>
            <p className="mt-0.5 text-sm text-amber-700">
              {isAdmin
                ? 'Como administrador podes modificarla igual. Cada cambio queda registrado en el historial de la internacion.'
                : 'Lo que se cargue ahora no lo vio el medico que firmo el alta. Si hace falta corregir algo, pedilo a un administrador.'}
            </p>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card className="p-6">
            <SectionTitle icon={<FileText className="h-5 w-5 text-teal-600" />}>
              Informacion de la internacion
            </SectionTitle>
            <div className="space-y-3">
              <div>
                <p className="mb-1 text-sm font-medium text-slate-500">Motivo de ingreso</p>
                <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-700">
                  {hosp.admission_reason}
                </p>
              </div>
              <InfoRow
                label="Edad al momento de la internacion"
                value={
                  patientAgeAtAdmission !== null ? `${patientAgeAtAdmission} años` : 'No disponible'
                }
              />
            </div>
          </Card>

          <LifecycleCard hosp={hosp} />
          <AdmissionCard hosp={hosp} />
          <BedManagementCard hosp={hosp} canManage={canManage} />
          <PracticesCard hosp={hosp} canManage={canManage} />
          <DiagnosesCard hosp={hosp} canManage={canManage} />
          <AccountCard hosp={hosp} canManage={canManage} />
          <DischargeCard hosp={hosp} canManage={canManage} />
          <DischargePrescriptionsCard hosp={hosp} canManage={canManage} />
        </div>

        <div className="space-y-6">
          <Card className="p-6">
            <SectionTitle icon={<User className="h-5 w-5 text-teal-600" />}>
              Datos del paciente
            </SectionTitle>
            {patient ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3 rounded-lg bg-slate-50 p-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-cyan-600 text-sm font-bold text-white">
                    {patient.first_name.charAt(0)}
                    {patient.last_name.charAt(0)}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-700">
                      {patient.first_name} {patient.last_name}
                    </p>
                    <p className="text-xs text-slate-400">
                      {patient.document_type}: {patient.document_number}
                    </p>
                  </div>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Fecha nacimiento</span>
                    <span className="font-medium text-slate-600">
                      {formatDate(patient.birth_date) ?? '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Registrado</span>
                    <span className="font-medium text-slate-600">
                      {new Date(patient.created_at).toLocaleDateString('es-ES')}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-400">No se encontraron datos del paciente.</p>
            )}
          </Card>

          <ServiceAssignmentsCard hosp={hosp} canManage={canManage} />
          <CareTeamCard hosp={hosp} canManage={canManage} />
          <EventsCard hospitalizationId={hosp.id} />
        </div>
      </div>
    </div>
  );
}
