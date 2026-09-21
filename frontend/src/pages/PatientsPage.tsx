import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { PatientCreate, PatientRead, PatientUpdate } from '@/api/model';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader, Card, Spinner, ErrorState, EmptyState } from '@/components/ui';
import Modal from '@/components/Modal';
import PatientCoveragesModal from '@/components/coverage/PatientCoveragesModal';
import { FileText, Pencil, Search, ShieldPlus, Trash2, UserPlus } from 'lucide-react';

const DOC_TYPES = ['DNI', 'NIE', 'PASSPORT', 'CIF'];

type PatientForm = PatientCreate | PatientUpdate;

const emptyPatientForm: PatientForm = {
  first_name: '',
  last_name: '',
  document_type: 'DNI',
  document_number: '',
  birth_date: null,
};

export default function PatientsPage() {
  const { can } = useAuth();
  const api = getDefault();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPatient, setEditingPatient] = useState<PatientRead | null>(null);
  const [coveragesOf, setCoveragesOf] = useState<PatientRead | null>(null);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState<PatientForm>(emptyPatientForm);

  const canManage = can('ADMISSION');

  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });

  const invalidatePatients = () => {
    queryClient.invalidateQueries({ queryKey: ['patients'] });
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingPatient(null);
    setForm(emptyPatientForm);
  };

  const createPatient = useMutation({
    mutationFn: (data: PatientCreate) => api.createPatientApiV1PatientsPost(data),
    onSuccess: () => {
      invalidatePatients();
      closeModal();
    },
  });

  const updatePatient = useMutation({
    mutationFn: ({ id, data }: { id: string; data: PatientUpdate }) =>
      api.updatePatientApiV1PatientsPatientIdPut(id, data),
    onSuccess: () => {
      invalidatePatients();
      closeModal();
    },
  });

  const deletePatient = useMutation({
    mutationFn: (id: string) => api.deletePatientApiV1PatientsPatientIdDelete(id),
    onSuccess: invalidatePatients,
  });

  const openCreate = () => {
    setEditingPatient(null);
    setForm(emptyPatientForm);
    setModalOpen(true);
  };

  const openEdit = (patient: PatientRead) => {
    setEditingPatient(patient);
    setForm({
      first_name: patient.first_name,
      last_name: patient.last_name,
      document_type: patient.document_type,
      document_number: patient.document_number,
      birth_date: patient.birth_date,
    });
    setModalOpen(true);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (editingPatient) {
      updatePatient.mutate({ id: editingPatient.id, data: form });
      return;
    }
    createPatient.mutate(form);
  };

  const patients = patientsQuery.data ?? [];
  const filtered = patients.filter((patient) => {
    const query = search.toLowerCase();
    return (
      patient.first_name.toLowerCase().includes(query) ||
      patient.last_name.toLowerCase().includes(query) ||
      patient.document_number.toLowerCase().includes(query)
    );
  });
  const saving = createPatient.isPending || updatePatient.isPending;

  return (
    <div>
      <PageHeader
        title="Pacientes"
        subtitle="Gestion y registro de pacientes"
        action={
          canManage ? (
            <button
              onClick={openCreate}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
            >
              <UserPlus className="h-4 w-4" />
              Nuevo paciente
            </button>
          ) : undefined
        }
      />

      <div className="mb-6">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nombre o documento..."
            className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-700 outline-none transition-all focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
          />
        </div>
      </div>

      {patientsQuery.isLoading && <Spinner />}
      {patientsQuery.isError && <ErrorState message="No se pudo cargar la lista de pacientes." />}

      {patientsQuery.data && (
        <Card className="overflow-hidden">
          {filtered.length === 0 ? (
            <EmptyState message="No se encontraron pacientes." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Paciente
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Documento
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Fecha nacimiento
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Registro
                    </th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-slate-500">
                      Acciones
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {filtered.map((patient) => (
                    <tr key={patient.id} className="hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-cyan-600 text-xs font-bold text-white">
                            {patient.first_name.charAt(0)}
                            {patient.last_name.charAt(0)}
                          </div>
                          <span className="text-sm font-semibold text-slate-700">
                            {patient.first_name} {patient.last_name}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-4 text-sm text-slate-500">
                        {patient.document_type} - {patient.document_number}
                      </td>
                      <td className="px-5 py-4 text-sm text-slate-500">
                        {patient.birth_date ?? 'Sin informar'}
                      </td>
                      <td className="px-5 py-4 text-sm text-slate-400">
                        {new Date(patient.created_at).toLocaleDateString('es-ES')}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex justify-end gap-2">
                          <Link
                            to={`/patients/${patient.id}`}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Historia clinica"
                          >
                            <FileText className="h-4 w-4" />
                          </Link>
                          <button
                            onClick={() => setCoveragesOf(patient)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Coberturas del paciente"
                          >
                            <ShieldPlus className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => openEdit(patient)}
                            disabled={!canManage}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700 disabled:opacity-40"
                            title="Editar paciente"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              if (window.confirm(`Eliminar paciente "${patient.first_name} ${patient.last_name}"?`)) {
                                deletePatient.mutate(patient.id);
                              }
                            }}
                            disabled={!canManage || deletePatient.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                            title="Eliminar paciente"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Modal
        open={modalOpen}
        onClose={closeModal}
        title={editingPatient ? 'Editar paciente' : 'Nuevo paciente'}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Nombre"
              maxLength={100}
              value={form.first_name}
              onChange={(value) => setForm({ ...form, first_name: value })}
            />
            <Input
              label="Apellidos"
              maxLength={100}
              value={form.last_name}
              onChange={(value) => setForm({ ...form, last_name: value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-600">Tipo doc.</span>
              <select
                value={form.document_type}
                onChange={(event) => setForm({ ...form, document_type: event.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              >
                {DOC_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <Input
              label="Numero doc."
              value={form.document_number}
              onChange={(value) => setForm({ ...form, document_number: value })}
            />
          </div>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-600">
              Fecha nacimiento
            </span>
            <input
              type="date"
              value={form.birth_date ?? ''}
              onChange={(event) => setForm({ ...form, birth_date: event.target.value || null })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </label>

          {(createPatient.isError || updatePatient.isError || deletePatient.isError) && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              No se pudo completar la operación sobre el paciente.
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={closeModal}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </Modal>

      <PatientCoveragesModal
        patient={coveragesOf}
        open={coveragesOf !== null}
        onClose={() => setCoveragesOf(null)}
      />
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  maxLength?: number;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-600">{label}</span>
      <input
        type="text"
        required
        maxLength={maxLength}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
      />
    </label>
  );
}
