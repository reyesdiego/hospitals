import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getBedWorkflow } from '@/api/endpoints/bed-workflow/bed-workflow';
import { getDefault } from '@/api/endpoints/default/default';
import type { BedCreate, BedRead, BedStatus } from '@/api/model';
import { invalidateBeds } from '@/api/queryKeys';
import { useAuth } from '@/auth/AuthContext';
import { BedCard } from '@/components/BedCard';
import Modal from '@/components/Modal';
import { BED_STATUS_LABELS } from '@/components/StatusBadges';
import {
  ActionButton,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  PageHeader,
  SectionTitle,
  Spinner,
  inputClass,
} from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import {
  BedDouble,
  Brush,
  CheckCircle2,
  DoorOpen,
  History,
  Plus,
  SlidersHorizontal,
} from 'lucide-react';

/** Statuses an operator can set by hand: occupancy and reservation belong to the stay. */
const OPERATIONAL_STATUSES: BedStatus[] = [
  'AVAILABLE',
  'BLOCKED',
  'MAINTENANCE',
  'OUT_OF_SERVICE',
];

export default function BedsPage() {
  const { user, can } = useAuth();
  const api = getDefault();
  const bedApi = getBedWorkflow();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [movingBed, setMovingBed] = useState<BedRead | null>(null);
  const [targetRoomId, setTargetRoomId] = useState('');
  const [statusBed, setStatusBed] = useState<BedRead | null>(null);
  const [nextStatus, setNextStatus] = useState<BedStatus>('BLOCKED');
  const [statusReason, setStatusReason] = useState('');
  const [historyBed, setHistoryBed] = useState<BedRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canCreate = can('CATALOG');
  const canClean = can('BED_CLEANING');

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
  const historyQuery = useQuery({
    queryKey: ['bed-status-history', historyBed?.id],
    queryFn: () => bedApi.bedStatusHistoryApiV1BedsBedIdStatusHistoryGet(historyBed?.id ?? ''),
    enabled: Boolean(historyBed),
  });

  const [form, setForm] = useState<BedCreate>({ facility_id: '', room_id: '', code: '' });

  const onDone = () => {
    invalidateBeds(queryClient);
    setError(null);
  };

  const createMutation = useMutation({
    mutationFn: (data: BedCreate) => api.createBedApiV1BedsPost(data),
    onSuccess: () => {
      onDone();
      setModalOpen(false);
      setForm({ facility_id: '', room_id: '', code: '' });
    },
    onError: (err) => setError(apiErrorMessage(err, 'Error al crear la cama.')),
  });

  const moveMutation = useMutation({
    mutationFn: ({ bedId, roomId }: { bedId: string; roomId: string }) =>
      api.assignBedRoomApiV1BedsBedIdRoomPost(bedId, { room_id: roomId }),
    onSuccess: () => {
      onDone();
      setMovingBed(null);
      setTargetRoomId('');
    },
    onError: (err) => setError(apiErrorMessage(err, 'Error al mover la cama.')),
  });

  const startCleaningMutation = useMutation({
    mutationFn: (bedId: string) =>
      bedApi.startBedCleaningApiV1BedsBedIdCleaningStartPost(bedId, {
        changed_by: user?.full_name ?? null,
      }),
    onSuccess: onDone,
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo iniciar la limpieza.')),
  });

  const completeCleaningMutation = useMutation({
    mutationFn: (bedId: string) =>
      bedApi.completeBedCleaningApiV1BedsBedIdCleaningCompletePost(bedId, {
        changed_by: user?.full_name ?? null,
      }),
    onSuccess: onDone,
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo finalizar la limpieza.')),
  });

  const statusMutation = useMutation({
    mutationFn: ({ bedId, status }: { bedId: string; status: BedStatus }) =>
      api.setBedStatusApiV1BedsBedIdStatusPost(bedId, {
        status,
        changed_by: user?.full_name ?? null,
        reason: statusReason || null,
      }),
    onSuccess: () => {
      onDone();
      setStatusBed(null);
      setStatusReason('');
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo cambiar el estado de la cama.')),
  });

  const beds = bedsQuery.data ?? [];
  const rooms = roomsQuery.data ?? [];
  const roomsForFacility = rooms.filter((room) => room.facility_id === form.facility_id);
  const moveRooms = movingBed
    ? rooms.filter(
        (room) => room.facility_id === movingBed.facility_id && room.id !== movingBed.room_id,
      )
    : [];
  const busy =
    startCleaningMutation.isPending ||
    completeCleaningMutation.isPending ||
    statusMutation.isPending;

  const wards = beds.reduce<Record<string, BedRead[]>>((acc, bed) => {
    (acc[bed.ward] ??= []).push(bed);
    return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="Camas"
        subtitle="Inventario, ocupacion, reservas y limpieza"
        action={
          canCreate ? (
            <ActionButton tone="primary" onClick={() => setModalOpen(true)} className="px-4 py-2.5">
              <Plus className="h-4 w-4" />
              Nueva cama
            </ActionButton>
          ) : undefined
        }
      />

      {(bedsQuery.isLoading || roomsQuery.isLoading) && <Spinner />}
      {(bedsQuery.isError || roomsQuery.isError) && (
        <ErrorState message="No se pudo cargar la lista de camas." />
      )}

      {error && (
        <div className="mb-4">
          <FormError message={error} />
        </div>
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
                  <SectionTitle icon={<BedDouble className="h-5 w-5 text-teal-600" />}>
                    {ward}
                    <span className="text-sm font-normal text-slate-400">
                      ({wardBeds.length})
                    </span>
                  </SectionTitle>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {wardBeds.map((bed) => (
                      <div key={bed.id} className="rounded-lg border border-slate-100 bg-white p-2">
                        <BedCard bed={bed} />
                        {canClean && (
                          <div className="mt-2 grid gap-2">
                            {bed.status === 'PENDING_CLEANING' && (
                              <ActionButton
                                tone="warning"
                                disabled={busy}
                                onClick={() => startCleaningMutation.mutate(bed.id)}
                                className="w-full text-xs"
                              >
                                <Brush className="h-3.5 w-3.5" />
                                Iniciar limpieza
                              </ActionButton>
                            )}
                            {(bed.status === 'CLEANING' || bed.status === 'PENDING_CLEANING') && (
                              <ActionButton
                                tone="success"
                                disabled={busy}
                                onClick={() => completeCleaningMutation.mutate(bed.id)}
                                className="w-full text-xs"
                              >
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                Finalizar limpieza
                              </ActionButton>
                            )}
                            <div className="grid grid-cols-2 gap-2">
                              <ActionButton
                                tone="neutral"
                                onClick={() => {
                                  setError(null);
                                  setStatusBed(bed);
                                  setNextStatus(
                                    bed.status === 'AVAILABLE' ? 'BLOCKED' : 'AVAILABLE',
                                  );
                                }}
                                className="text-xs"
                              >
                                <SlidersHorizontal className="h-3.5 w-3.5" />
                                Estado
                              </ActionButton>
                              <ActionButton
                                tone="neutral"
                                onClick={() => setHistoryBed(bed)}
                                className="text-xs"
                              >
                                <History className="h-3.5 w-3.5" />
                                Historial
                              </ActionButton>
                            </div>
                            <ActionButton
                              tone="neutral"
                              onClick={() => {
                                setMovingBed(bed);
                                setTargetRoomId('');
                              }}
                              className="w-full text-xs"
                            >
                              <DoorOpen className="h-3.5 w-3.5" />
                              Mover habitacion
                            </ActionButton>
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
        <form
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate(form);
          }}
          className="space-y-4"
        >
          <Field label="Centro sanitario">
            <select
              required
              value={form.facility_id}
              onChange={(e) => setForm({ ...form, facility_id: e.target.value, room_id: '' })}
              className={inputClass}
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
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Codigo">
              <input
                type="text"
                required
                placeholder="A-101"
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label="Habitacion">
              <select
                required
                value={form.room_id}
                onChange={(e) => setForm({ ...form, room_id: e.target.value })}
                className={inputClass}
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
            </Field>
          </div>
          {form.facility_id && roomsForFacility.length === 0 && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
              El centro seleccionado no tiene habitaciones disponibles para asociar camas.
            </p>
          )}
          <FormError message={createMutation.isError ? error : null} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setModalOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="primary"
              type="submit"
              disabled={
                createMutation.isPending || facilitiesQuery.data?.length === 0 || !form.room_id
              }
            >
              {createMutation.isPending ? 'Guardando...' : 'Guardar'}
            </ActionButton>
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
            className={inputClass}
          >
            <option value="">Selecciona habitacion</option>
            {moveRooms.map((room) => (
              <option key={room.id} value={room.id}>
                Hab. {room.code} - {room.ward}
              </option>
            ))}
          </select>
          <FormError message={moveMutation.isError ? error : null} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setMovingBed(null)}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={moveMutation.isPending || !targetRoomId}>
              {moveMutation.isPending ? 'Moviendo...' : 'Mover'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!statusBed}
        onClose={() => setStatusBed(null)}
        title={`Estado operativo de ${statusBed?.code ?? ''}`}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (statusBed) statusMutation.mutate({ bedId: statusBed.id, status: nextStatus });
          }}
          className="space-y-4"
        >
          <p className="text-sm text-slate-500">
            La ocupacion y la reserva se gestionan desde la internacion. Una cama ocupada o
            reservada no puede cambiar de estado operativo.
          </p>
          <Field label="Nuevo estado">
            <select
              value={nextStatus}
              onChange={(event) => setNextStatus(event.target.value as BedStatus)}
              className={inputClass}
            >
              {OPERATIONAL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {BED_STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Motivo">
            <input
              type="text"
              value={statusReason}
              onChange={(event) => setStatusReason(event.target.value)}
              placeholder="Obra en la habitacion"
              className={inputClass}
            />
          </Field>
          <FormError message={statusMutation.isError ? error : null} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setStatusBed(null)}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={statusMutation.isPending}>
              {statusMutation.isPending ? 'Guardando...' : 'Cambiar estado'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!historyBed}
        onClose={() => setHistoryBed(null)}
        title={`Historial de ${historyBed?.code ?? ''}`}
      >
        {historyQuery.isLoading ? (
          <Spinner />
        ) : (historyQuery.data ?? []).length === 0 ? (
          <EmptyState message="Sin cambios de estado registrados." />
        ) : (
          <ol className="space-y-3">
            {(historyQuery.data ?? []).map((entry) => (
              <li key={entry.id} className="border-l-2 border-slate-100 pl-4">
                <p className="text-sm font-semibold text-slate-700">
                  {entry.previous_status
                    ? `${BED_STATUS_LABELS[entry.previous_status]} → ${BED_STATUS_LABELS[entry.new_status]}`
                    : BED_STATUS_LABELS[entry.new_status]}
                </p>
                <p className="text-xs text-slate-400">
                  {formatDateTime(entry.changed_at)}
                  {entry.changed_by ? ` · ${entry.changed_by}` : ''}
                  {entry.reason ? ` · ${entry.reason}` : ''}
                </p>
              </li>
            ))}
          </ol>
        )}
      </Modal>
    </div>
  );
}
