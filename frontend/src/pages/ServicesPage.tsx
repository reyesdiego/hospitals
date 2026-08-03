import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { ServiceCreate, ServiceRead } from '@/api/model';
import { PageHeader, Card, Spinner, ErrorState, EmptyState } from '@/components/ui';
import Modal from '@/components/Modal';
import { Pencil, Plus, Stethoscope, Trash2 } from 'lucide-react';

type ServiceForm = ServiceCreate;

const emptyForm: ServiceForm = { name: '', code: '' };

export default function ServicesPage() {
  const api = getDefault();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceRead | null>(null);
  const [form, setForm] = useState<ServiceForm>(emptyForm);

  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => api.listServicesApiV1ServicesGet(),
  });

  const createMutation = useMutation({
    mutationFn: (data: ServiceCreate) => api.createServiceApiV1ServicesPost(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ serviceId, data }: { serviceId: string; data: ServiceForm }) =>
      api.updateServiceApiV1ServicesServiceIdPut(serviceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (serviceId: string) => api.deleteServiceApiV1ServicesServiceIdDelete(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (service: ServiceRead) => {
    setEditing(service);
    setForm({ name: service.name, code: service.code });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditing(null);
    setForm(emptyForm);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (editing) {
      updateMutation.mutate({ serviceId: editing.id, data: form });
      return;
    }
    createMutation.mutate(form);
  };

  const handleDelete = (service: ServiceRead) => {
    if (!window.confirm(`Eliminar servicio "${service.name}"?`)) return;
    deleteMutation.mutate(service.id);
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const hasMutationError =
    createMutation.isError || updateMutation.isError || deleteMutation.isError;
  const services = servicesQuery.data ?? [];

  return (
    <div>
      <PageHeader
        title="Servicios"
        subtitle="Catalogo de servicios hospitalarios"
        action={
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
          >
            <Plus className="h-4 w-4" />
            Nuevo servicio
          </button>
        }
      />

      {servicesQuery.isLoading && <Spinner />}
      {servicesQuery.isError && <ErrorState message="No se pudo cargar la lista de servicios." />}

      {hasMutationError && (
        <Card className="mb-4 border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm font-medium text-red-600">
            No se pudo completar la operacion solicitada.
          </p>
        </Card>
      )}

      {servicesQuery.data && (
        <Card className="overflow-hidden">
          {services.length === 0 ? (
            <EmptyState message="No hay servicios registrados." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Servicio
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Codigo
                    </th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-slate-500">
                      Acciones
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {services.map((service) => (
                    <tr key={service.id} className="hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50">
                            <Stethoscope className="h-5 w-5 text-teal-600" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-slate-800">
                              {service.name}
                            </p>
                            <p className="text-xs text-slate-400">
                              Creado el {new Date(service.created_at).toLocaleDateString('es-ES')}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
                          {service.code}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => openEdit(service)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Editar servicio"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(service)}
                            disabled={deleteMutation.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                            title="Eliminar servicio"
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
        title={editing ? 'Editar servicio' : 'Nuevo servicio'}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Nombre
            </label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Codigo
            </label>
            <input
              type="text"
              required
              value={form.code}
              onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>

          {(createMutation.isError || updateMutation.isError) && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al guardar el servicio.
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
              disabled={isSaving}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {isSaving ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
