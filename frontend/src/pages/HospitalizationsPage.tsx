import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { HospitalizationCreate, BedAssignmentCreate } from '@/api/model';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader, Card, Spinner, ErrorState, EmptyState } from '@/components/ui';
import { HospitalizationStatusBadge } from '@/components/StatusBadges';
import Modal from '@/components/Modal';
import { ClipboardPlus, Plus, BedDouble, Unlock } from 'lucide-react';

export default function HospitalizationsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const api = getDefault();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [assignHospId, setAssignHospId] = useState<string | null>(null);

  const canCreate = user && ['admin', 'doctor', 'nurse'].includes(user.role);

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

  const [hospForm, setHospForm] = useState<HospitalizationCreate>({
    patient_id: '',
    admission_reason: '',
  });

  const createHospMutation = useMutation({
    mutationFn: (data: HospitalizationCreate) =>
      api.createHospitalizationApiV1HospitalizationsPost(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
      setCreateOpen(false);
      setHospForm({ patient_id: '', admission_reason: '' });
    },
  });

  const [assignBedId, setAssignBedId] = useState('');

  const assignMutation = useMutation({
    mutationFn: ({ hospId, bedId }: { hospId: string; bedId: string }) => {
      const body: BedAssignmentCreate = { bed_id: bedId };
      return api.assignBedApiV1HospitalizationsHospitalizationIdBedAssignmentsPost(hospId, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
      setAssignHospId(null);
      setAssignBedId('');
    },
  });

  const releaseMutation = useMutation({
    mutationFn: (hospId: string) =>
      api.releaseBedApiV1HospitalizationsHospitalizationIdReleaseBedPost(hospId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
    },
  });

  const isLoading = patientsQuery.isLoading || bedsQuery.isLoading || hospitalizationsQuery.isLoading;
  const isError = patientsQuery.isError || bedsQuery.isError || hospitalizationsQuery.isError;

  const patients = patientsQuery.data ?? [];
  const beds = bedsQuery.data ?? [];
  const hospitalizations = hospitalizationsQuery.data ?? [];
  const availableBeds = beds.filter((b) => b.status === 'AVAILABLE');

  const handleCreateHosp = (e: React.FormEvent) => {
    e.preventDefault();
    createHospMutation.mutate(hospForm);
  };

  const handleAssign = (e: React.FormEvent) => {
    e.preventDefault();
    if (!assignHospId || !assignBedId) return;
    assignMutation.mutate({ hospId: assignHospId, bedId: assignBedId });
  };

  return (
    <div>
      <PageHeader
        title="Hospitalizaciones"
        subtitle="Admisiones, asignacion de camas y altas"
        action={
          canCreate ? (
            <button
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
            >
              <Plus className="h-4 w-4" />
              Nueva hospitalizacion
            </button>
          ) : undefined
        }
      />

      {isLoading && <Spinner />}
      {isError && <ErrorState message="No se pudieron cargar los datos." />}

      {!isLoading && !isError && (
        <>
          {hospitalizations.length === 0 ? (
            <Card className="p-6">
              <EmptyState message="No hay hospitalizaciones registradas. Crea una nueva para comenzar." />
            </Card>
          ) : (
            <div className="space-y-4">
              {hospitalizations.map((h) => {
                const patient = patients.find((p) => p.id === h.patient_id);
                const patientName = patient
                  ? `${patient.first_name} ${patient.last_name}`
                  : 'Paciente desconocido';

                return (
                  <Card
                    key={h.id}
                    className="cursor-pointer p-5 transition-all hover:border-teal-300 hover:shadow-md"
                    onClick={() => navigate(`/hospitalizations/${h.id}`)}
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex items-start gap-4">
                        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-teal-50">
                          <ClipboardPlus className="h-6 w-6 text-teal-600" />
                        </div>
                        <div>
                          <p className="text-base font-bold text-slate-800">{patientName}</p>
                          <p className="text-sm text-slate-500">{h.admission_reason}</p>
                          <div className="mt-2 flex items-center gap-3">
                            <HospitalizationStatusBadge status={h.status as never} />
                            {h.admitted_at && (
                              <span className="text-xs text-slate-400">
                                Ingreso: {new Date(h.admitted_at).toLocaleString('es-ES')}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                        {h.status === 'PENDING_BED' && canCreate && (
                          <button
                            onClick={() => setAssignHospId(h.id)}
                            className="flex items-center gap-1.5 rounded-lg bg-teal-50 px-3 py-2 text-sm font-semibold text-teal-700 transition-colors hover:bg-teal-100"
                          >
                            <BedDouble className="h-4 w-4" />
                            Asignar cama
                          </button>
                        )}
                        {h.status === 'IN_PROGRESS' && canCreate && (
                          <button
                            onClick={() => releaseMutation.mutate(h.id)}
                            disabled={releaseMutation.isPending}
                            className="flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-700 transition-colors hover:bg-amber-100 disabled:opacity-50"
                          >
                            <Unlock className="h-4 w-4" />
                            Liberar cama
                          </button>
                        )}
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Create hospitalization modal */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Nueva hospitalizacion">
        <form onSubmit={handleCreateHosp} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">Paciente</label>
            <select
              required
              value={hospForm.patient_id}
              onChange={(e) => setHospForm({ ...hospForm, patient_id: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            >
              <option value="">Selecciona un paciente...</option>
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.first_name} {p.last_name} - {p.document_number}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Motivo de ingreso
            </label>
            <textarea
              required
              minLength={3}
              maxLength={500}
              rows={3}
              placeholder="Describe el motivo de la hospitalizacion..."
              value={hospForm.admission_reason}
              onChange={(e) => setHospForm({ ...hospForm, admission_reason: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>

          {createHospMutation.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al crear la hospitalizacion.
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={createHospMutation.isPending}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {createHospMutation.isPending ? 'Guardando...' : 'Crear'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Assign bed modal */}
      <Modal open={!!assignHospId} onClose={() => setAssignHospId(null)} title="Asignar cama">
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
              onClick={() => setAssignHospId(null)}
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
