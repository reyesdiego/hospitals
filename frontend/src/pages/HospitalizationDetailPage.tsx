import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { BedAssignmentCreate } from '@/api/model';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader, Card, Spinner, ErrorState } from '@/components/ui';
import { HospitalizationStatusBadge } from '@/components/StatusBadges';
import Modal from '@/components/Modal';
import { ArrowLeft, BedDouble, Unlock, User, Calendar, FileText } from 'lucide-react';

export default function HospitalizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const api = getDefault();
  const queryClient = useQueryClient();
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignBedId, setAssignBedId] = useState('');

  const canManage = user && ['admin', 'doctor', 'nurse'].includes(user.role);

  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });
  const bedsQuery = useQuery({
    queryKey: ['beds'],
    queryFn: () => api.listBedsApiV1BedsGet(),
  });
  const hospitalizationsQuery = useQuery({
    queryKey: ['hospitalizations'],
    queryFn: () => api.listHospitalizationsApiV1HospitalizationsGet(),
  });

  const hosp = hospitalizationsQuery.data?.find((h) => h.id === id);

  const availableBeds = (bedsQuery.data ?? []).filter((b) => b.status === 'AVAILABLE');

  const releaseMutation = useMutation({
    mutationFn: (hospId: string) =>
      api.releaseBedApiV1HospitalizationsHospitalizationIdReleaseBedPost(hospId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
      navigate('/hospitalizations');
    },
  });

  const assignMutation = useMutation({
    mutationFn: ({ hospId, bedId }: { hospId: string; bedId: string }) => {
      const body: BedAssignmentCreate = { bed_id: bedId };
      return api.assignBedApiV1HospitalizationsHospitalizationIdBedAssignmentsPost(hospId, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
      setAssignOpen(false);
      setAssignBedId('');
    },
  });

  if (patientsQuery.isLoading || bedsQuery.isLoading || hospitalizationsQuery.isLoading) {
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

  const patient = patientsQuery.data?.find((p) => p.id === hosp.patient_id);
  const patientName = patient
    ? `${patient.first_name} ${patient.last_name}`
    : 'Paciente desconocido';

  const handleAssign = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !assignBedId) return;
    assignMutation.mutate({ hospId: id, bedId: assignBedId });
  };

  return (
    <div>
      <button
        onClick={() => navigate('/hospitalizations')}
        className="mb-4 flex items-center gap-2 text-sm font-medium text-teal-600 transition-colors hover:text-teal-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Volver a hospitalizaciones
      </button>

      <PageHeader
        title={patientName}
        subtitle={`Hospitalizacion #${hosp.id.slice(0, 8)}`}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main info */}
        <div className="space-y-6 lg:col-span-2">
          <Card className="p-6">
            <h3 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800">
              <FileText className="h-5 w-5 text-teal-600" />
              Informacion de la hospitalizacion
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3">
                <span className="text-sm font-medium text-slate-500">Estado</span>
                <HospitalizationStatusBadge status={hosp.status as never} />
              </div>
              <div>
                <p className="mb-1 text-sm font-medium text-slate-500">Motivo de ingreso</p>
                <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-700">
                  {hosp.admission_reason}
                </p>
              </div>
              <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-4 py-3">
                <Calendar className="h-4 w-4 text-slate-400" />
                <span className="text-sm text-slate-500">Fecha de ingreso:</span>
                <span className="text-sm font-semibold text-slate-700">
                  {hosp.admitted_at
                    ? new Date(hosp.admitted_at).toLocaleString('es-ES')
                    : 'Pendiente de asignacion de cama'}
                </span>
              </div>
            </div>
          </Card>

          {/* Bed management */}
          <Card className="p-6">
            <h3 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800">
              <BedDouble className="h-5 w-5 text-teal-600" />
              Gestion de cama
            </h3>
            <div className="space-y-4">
              {canManage && hosp.status === 'PENDING_BED' && (
                <button
                  onClick={() => setAssignOpen(true)}
                  className="flex items-center gap-2 rounded-lg bg-teal-50 px-4 py-2.5 text-sm font-semibold text-teal-700 transition-colors hover:bg-teal-100"
                >
                  <BedDouble className="h-4 w-4" />
                  Asignar cama
                </button>
              )}
              {canManage && hosp.status === 'IN_PROGRESS' && (
                <button
                  onClick={() => releaseMutation.mutate(hosp.id)}
                  disabled={releaseMutation.isPending}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-50 px-4 py-2.5 text-sm font-semibold text-amber-700 transition-colors hover:bg-amber-100 disabled:opacity-50"
                >
                  <Unlock className="h-4 w-4" />
                  {releaseMutation.isPending ? 'Liberando...' : 'Liberar cama'}
                </button>
              )}
              {hosp.status !== 'PENDING_BED' && hosp.status !== 'IN_PROGRESS' && (
                <p className="text-sm text-slate-400">Sin acciones pendientes.</p>
              )}
            </div>
          </Card>
        </div>

        {/* Patient sidebar */}
        <div>
          <Card className="p-6">
            <h3 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800">
              <User className="h-5 w-5 text-teal-600" />
              Datos del paciente
            </h3>
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
                      {patient.birth_date ?? '—'}
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
              <p className="text-sm text-slate-400">
                No se encontraron datos del paciente.
              </p>
            )}
          </Card>
        </div>
      </div>

      {/* Assign bed modal */}
      <Modal open={assignOpen} onClose={() => setAssignOpen(false)} title="Asignar cama">
        <form onSubmit={handleAssign} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Cama disponible
            </label>
            {availableBeds.length === 0 ? (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
                No hay camas disponibles en este momento.
              </p>
            ) : (
              <select
                required
                value={assignBedId}
                onChange={(e) => setAssignBedId(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              >
                <option value="">Selecciona una cama...</option>
                {availableBeds.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.code} - {b.ward} (Hab. {b.room})
                  </option>
                ))}
              </select>
            )}
          </div>

          {assignMutation.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al asignar la cama.
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setAssignOpen(false)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={assignMutation.isPending || availableBeds.length === 0}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {assignMutation.isPending ? 'Asignando...' : 'Asignar'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
