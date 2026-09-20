import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { RoomCreate, RoomRead, RoomStatus, RoomUpdate } from '@/api/model';
import { Badge, Card, EmptyState, ErrorState, PageHeader, Spinner } from '@/components/ui';
import Modal from '@/components/Modal';
import { DoorOpen, Pencil, Plus, Trash2 } from 'lucide-react';

const STATUS_LABELS: Record<RoomStatus, string> = {
  AVAILABLE: 'Disponible',
  RESERVED: 'Reservada',
  OCCUPIED: 'Ocupada',
  PENDING_CLEANING: 'Limpieza',
  BLOCKED: 'Bloqueada',
  MAINTENANCE: 'Mantenimiento',
};

const STATUS_COLORS: Record<RoomStatus, string> = {
  AVAILABLE: 'bg-emerald-50 text-emerald-700',
  RESERVED: 'bg-blue-50 text-blue-700',
  OCCUPIED: 'bg-rose-50 text-rose-700',
  PENDING_CLEANING: 'bg-amber-50 text-amber-700',
  BLOCKED: 'bg-slate-100 text-slate-600',
  MAINTENANCE: 'bg-purple-50 text-purple-700',
};

const emptyForm: RoomUpdate = {
  facility_id: '',
  code: '',
  ward: '',
  status: 'AVAILABLE',
};

export default function RoomsPage() {
  const api = getDefault();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RoomRead | null>(null);
  const [form, setForm] = useState<RoomUpdate>(emptyForm);

  const roomsQuery = useQuery({
    queryKey: ['rooms'],
    queryFn: () => api.listRoomsApiV1RoomsGet(),
  });
  const facilitiesQuery = useQuery({
    queryKey: ['facilities'],
    queryFn: () => api.listFacilitiesApiV1FacilitiesGet(),
  });

  const createMutation = useMutation({
    mutationFn: (data: RoomCreate) => api.createRoomApiV1RoomsPost(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ roomId, data }: { roomId: string; data: RoomUpdate }) =>
      api.updateRoomApiV1RoomsRoomIdPut(roomId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (roomId: string) => api.deleteRoomApiV1RoomsRoomIdDelete(roomId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (room: RoomRead) => {
    setEditing(room);
    setForm({
      facility_id: room.facility_id,
      code: room.code,
      ward: room.ward,
      status: room.administrative_status,
    });
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
      updateMutation.mutate({ roomId: editing.id, data: form });
      return;
    }
    createMutation.mutate(form);
  };

  const handleDelete = (room: RoomRead) => {
    if (!window.confirm(`Eliminar habitacion "${room.code}"?`)) return;
    deleteMutation.mutate(room.id);
  };

  const rooms = roomsQuery.data ?? [];
  const facilities = facilitiesQuery.data ?? [];
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const hasError =
    roomsQuery.isError ||
    facilitiesQuery.isError ||
    createMutation.isError ||
    updateMutation.isError ||
    deleteMutation.isError;

  return (
    <div>
      <PageHeader
        title="Habitaciones"
        subtitle="Gestion de habitaciones por centro, ala y estado operativo"
        action={
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
          >
            <Plus className="h-4 w-4" />
            Nueva habitacion
          </button>
        }
      />

      {(roomsQuery.isLoading || facilitiesQuery.isLoading) && <Spinner />}
      {hasError && <ErrorState message="No se pudo completar la operacion de habitaciones." />}

      {roomsQuery.data && !hasError && (
        <Card className="overflow-hidden">
          {rooms.length === 0 ? (
            <EmptyState message="No hay habitaciones registradas." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Habitacion
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Centro
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Camas
                    </th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-slate-500">
                      Acciones
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {rooms.map((room) => {
                    const facility = facilities.find((item) => item.id === room.facility_id);
                    return (
                      <tr key={room.id} className="hover:bg-slate-50">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50">
                              <DoorOpen className="h-5 w-5 text-teal-600" />
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-slate-800">
                                Hab. {room.code}
                              </p>
                              <p className="text-xs text-slate-400">{room.ward}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4 text-sm text-slate-500">
                          {facility ? `${facility.name} (${facility.code})` : 'Centro desconocido'}
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <Badge
                              status={STATUS_LABELS[room.status]}
                              color={STATUS_COLORS[room.status]}
                            />
                            <span className="text-sm text-slate-500">
                              {room.available_beds}/{room.beds} cama(s) disponible(s)
                              {(room.cleaning_beds ?? 0) > 0 &&
                                `, ${room.cleaning_beds} en limpieza`}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => openEdit(room)}
                              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                              title="Editar habitacion"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(room)}
                              disabled={deleteMutation.isPending || (room.beds ?? 0) > 0}
                              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                              title={(room.beds ?? 0) > 0 ? 'Tiene camas asociadas' : 'Eliminar habitacion'}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Modal
        open={modalOpen}
        onClose={closeModal}
        title={editing ? 'Editar habitacion' : 'Nueva habitacion'}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Centro sanitario
            </label>
            <select
              required
              value={form.facility_id}
              onChange={(event) => setForm({ ...form, facility_id: event.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            >
              <option value="">Selecciona un centro</option>
              {facilities.map((facility) => (
                <option key={facility.id} value={facility.id}>
                  {facility.name} ({facility.code})
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Codigo</label>
              <input
                required
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Estado</label>
              <select
                value={form.status}
                onChange={(event) =>
                  setForm({ ...form, status: event.target.value as RoomStatus })
                }
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              >
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">Ala / sector</label>
            <input
              required
              value={form.ward}
              onChange={(event) => setForm({ ...form, ward: event.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>

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
