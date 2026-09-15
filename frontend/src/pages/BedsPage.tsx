import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { BedCreate, BedRead } from '@/api/model';
import { useAuth } from '@/auth/AuthContext';
import { BedCard } from '@/components/BedCard';
import { PageHeader, Card, Spinner, ErrorState, EmptyState } from '@/components/ui';
import Modal from '@/components/Modal';
import { BedDouble, CheckCircle2, DoorOpen, Plus } from 'lucide-react';

export default function BedsPage() {
  const { user } = useAuth();
  const api = getDefault();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [movingBed, setMovingBed] = useState<BedRead | null>(null);
  const [targetRoomId, setTargetRoomId] = useState('');

  const canCreate = user && ['admin', 'nurse'].includes(user.role);

  const bedsQuery = useQuery({
    queryKey: ['beds'],
    queryFn: () => api.listBedsApiV1BedsGet(),
  });

  const facilitiesQuery = useQuery({
    queryKey: ['facilities'],
    queryFn: () => api.listFacilitiesApiV1FacilitiesGet(),
  });
  const roomsQuery = useQuery({
    queryKey: ['rooms'],
    queryFn: () => api.listRoomsApiV1RoomsGet(),
  });

  const [form, setForm] = useState<BedCreate>({
    facility_id: '',
    room_id: '',
    code: '',
  });

  const createMutation = useMutation({
    mutationFn: (data: BedCreate) => api.createBedApiV1BedsPost(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      setModalOpen(false);
      setForm({ facility_id: '', room_id: '', code: '' });
    },
  });

  const moveMutation = useMutation({
    mutationFn: ({ bedId, roomId }: { bedId: string; roomId: string }) =>
      api.assignBedRoomApiV1BedsBedIdRoomPost(bedId, { room_id: roomId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      setMovingBed(null);
      setTargetRoomId('');
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ bedId, status }: { bedId: string; status: 'AVAILABLE' }) =>
      api.setBedStatusApiV1BedsBedIdStatusPost(bedId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(form);
  };

  const beds = bedsQuery.data ?? [];
  const rooms = roomsQuery.data ?? [];
  const roomsForFacility = rooms.filter((room) => room.facility_id === form.facility_id);
  const moveRooms = movingBed
    ? rooms.filter((room) => room.facility_id === movingBed.facility_id && room.id !== movingBed.room_id)
    : [];

  // Group by ward
  const wards = beds.reduce<Record<string, typeof beds>>((acc, bed) => {
    (acc[bed.ward] ??= []).push(bed);
    return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="Camas"
        subtitle="Inventario y estado de camas por servicio"
        action={
          canCreate ? (
            <button
              onClick={() => setModalOpen(true)}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
            >
              <Plus className="h-4 w-4" />
              Nueva cama
            </button>
          ) : undefined
        }
      />

      {(bedsQuery.isLoading || roomsQuery.isLoading) && <Spinner />}
      {(bedsQuery.isError || roomsQuery.isError) && (
        <ErrorState message="No se pudo cargar la lista de camas." />
      )}

      {bedsQuery.data && (
        <>
          {beds.length === 0 ? (
            <Card className="p-6">
              <EmptyState message="No hay camas registradas." />
            </Card>
          ) : (
            <div className="space-y-6">
              {Object.entries(wards).map(([ward, wardBeds]) => (
                <Card key={ward} className="p-6">
                  <h3 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800">
                    <BedDouble className="h-5 w-5 text-teal-600" />
                    {ward}
                    <span className="text-sm font-normal text-slate-400">
                      ({wardBeds.length})
                    </span>
                  </h3>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {wardBeds.map((bed) => (
                      <div key={bed.id} className="rounded-lg border border-slate-100 bg-white p-2">
                        <BedCard bed={bed} />
                        {canCreate && (
                          <div className="mt-2 grid gap-2">
                            {bed.status === 'PENDING_CLEANING' && (
                              <button
                                type="button"
                                onClick={() =>
                                  statusMutation.mutate({ bedId: bed.id, status: 'AVAILABLE' })
                                }
                                disabled={statusMutation.isPending}
                                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                              >
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                Marcar disponible
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => {
                                setMovingBed(bed);
                                setTargetRoomId('');
                              }}
                              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                            >
                              <DoorOpen className="h-3.5 w-3.5" />
                              Mover habitacion
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Nueva cama">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Centro sanitario
            </label>
            <select
              required
              value={form.facility_id}
              onChange={(e) => setForm({ ...form, facility_id: e.target.value, room_id: '' })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              disabled={facilitiesQuery.isLoading || facilitiesQuery.isError}
            >
              <option value="">
                {facilitiesQuery.isLoading
                  ? 'Cargando centros...'
                  : facilitiesQuery.isError
                    ? 'No se pudieron cargar los centros'
                    : 'Selecciona un centro'}
              </option>
              {(facilitiesQuery.data ?? []).map((facility) => (
                <option key={facility.id} value={facility.id}>
                  {facility.name} ({facility.code})
                </option>
              ))}
            </select>
            {facilitiesQuery.data?.length === 0 && (
              <p className="mt-1.5 text-xs text-slate-500">
                Primero crea un centro sanitario para poder dar de alta camas.
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Codigo</label>
              <input
                type="text"
                required
                placeholder="A-101"
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">Habitacion</label>
              <select
                required
                value={form.room_id}
                onChange={(e) => setForm({ ...form, room_id: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
                disabled={!form.facility_id}
              >
                <option value="">
                  {form.facility_id ? 'Selecciona habitacion' : 'Selecciona centro primero'}
                </option>
                {roomsForFacility.map((room) => (
                  <option key={room.id} value={room.id}>
                    Hab. {room.code} - {room.ward}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {form.facility_id && roomsForFacility.length === 0 && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
              El centro seleccionado no tiene habitaciones disponibles para asociar camas.
            </p>
          )}

          {createMutation.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al crear la cama.
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
              disabled={
                createMutation.isPending ||
                facilitiesQuery.data?.length === 0 ||
                !form.room_id
              }
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {createMutation.isPending ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={!!movingBed} onClose={() => setMovingBed(null)} title="Mover cama">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!movingBed || !targetRoomId) return;
            moveMutation.mutate({ bedId: movingBed.id, roomId: targetRoomId });
          }}
          className="space-y-4"
        >
          <p className="text-sm text-slate-500">
            {movingBed?.code} esta en Hab. {movingBed?.room}. Selecciona la nueva habitacion.
          </p>
          <select
            required
            value={targetRoomId}
            onChange={(event) => setTargetRoomId(event.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
          >
            <option value="">Selecciona habitacion</option>
            {moveRooms.map((room) => (
              <option key={room.id} value={room.id}>
                Hab. {room.code} - {room.ward}
              </option>
            ))}
          </select>
          {moveMutation.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al mover la cama.
            </p>
          )}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setMovingBed(null)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={moveMutation.isPending || !targetRoomId}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {moveMutation.isPending ? 'Moviendo...' : 'Mover'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
