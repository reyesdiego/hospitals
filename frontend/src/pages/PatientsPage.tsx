import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { PatientCreate } from '@/api/model';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader, Card, Spinner, ErrorState, EmptyState } from '@/components/ui';
import Modal from '@/components/Modal';
import { Users, UserPlus, Search } from 'lucide-react';

const DOC_TYPES = ['DNI', 'NIE', 'PASSPORT', 'CIF'];

export default function PatientsPage() {
  const { user } = useAuth();
  const api = getDefault();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [search, setSearch] = useState('');

  const canCreate = user && ['admin', 'doctor', 'nurse', 'receptionist'].includes(user.role);

  const query = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });

  const createMutation = useMutation({
    mutationFn: (data: PatientCreate) => api.createPatientApiV1PatientsPost(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['patients'] });
      setModalOpen(false);
    },
  });

  const [form, setForm] = useState<PatientCreate>({
    first_name: '',
    last_name: '',
    document_type: 'DNI',
    document_number: '',
    birth_date: null,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(form);
  };

  const filtered = (query.data ?? []).filter((p) => {
    const q = search.toLowerCase();
    return (
      p.first_name.toLowerCase().includes(q) ||
      p.last_name.toLowerCase().includes(q) ||
      p.document_number.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <PageHeader
        title="Pacientes"
        subtitle="Gestion y registro de pacientes"
        action={
          canCreate ? (
            <button
              onClick={() => setModalOpen(true)}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
            >
              <UserPlus className="h-4 w-4" />
              Nuevo paciente
            </button>
          ) : undefined
        }
      />

      {/* Search */}
      <div className="mb-6">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nombre o documento..."
            className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-700 outline-none transition-all focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
          />
        </div>
      </div>

      {query.isLoading && <Spinner />}
      {query.isError && <ErrorState message="No se pudo cargar la lista de pacientes." />}

      {query.data && (
        <Card className="overflow-hidden">
          {filtered.length === 0 ? (
            <EmptyState message="No se encontraron pacientes." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                    <th className="px-6 py-3">Paciente</th>
                    <th className="px-6 py-3">Documento</th>
                    <th className="px-6 py-3">Fecha nacimiento</th>
                    <th className="px-6 py-3">Registro</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {filtered.map((p) => (
                    <tr key={p.id} className="transition-colors hover:bg-slate-50">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-cyan-600 text-xs font-bold text-white">
                            {p.first_name.charAt(0)}
                            {p.last_name.charAt(0)}
                          </div>
                          <span className="text-sm font-semibold text-slate-700">
                            {p.first_name} {p.last_name}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">
                        {p.document_type} - {p.document_number}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">
                        {p.birth_date ?? '—'}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {new Date(p.created_at).toLocaleDateString('es-ES')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Create modal */}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Nuevo paciente">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Nombre</label>
              <input
                type="text"
                required
                maxLength={100}
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Apellidos</label>
              <input
                type="text"
                required
                maxLength={100}
                value={form.last_name}
                onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Tipo doc.</label>
              <select
                value={form.document_type}
                onChange={(e) => setForm({ ...form, document_type: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              >
                {DOC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Numero doc.</label>
              <input
                type="text"
                required
                value={form.document_number}
                onChange={(e) => setForm({ ...form, document_number: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Fecha nacimiento (opcional)
            </label>
            <input
              type="date"
              value={form.birth_date ?? ''}
              onChange={(e) => setForm({ ...form, birth_date: e.target.value || null })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>

          {createMutation.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al crear el paciente. Verifica los datos.
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setModalOpen(false)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {createMutation.isPending ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
