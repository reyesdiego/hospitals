import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getBedWorkflow } from '@/api/endpoints/bed-workflow/bed-workflow';
import { getDefault } from '@/api/endpoints/default/default';
import type {
  AdmissionArrivalCreate,
  AdmissionDashboardRead,
  BedRead,
  BedReservationRead,
  ConsentType,
  HospitalizationRead,
} from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import Modal from '@/components/Modal';
import { BedStatusBadge } from '@/components/StatusBadges';
import AvailableBedSelect from '@/components/beds/AvailableBedSelect';
import {
  ActionButton,
  Card,
  Field,
  FormError,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import { RESERVATION_STATUS_COLORS, RESERVATION_STATUS_LABELS } from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime, minutesUntil } from '@/utils/format';
import { ArrowRightLeft, BedDouble, CalendarClock, LogIn, XCircle } from 'lucide-react';

const OPEN_STATUSES = ['AWAITING_ARRIVAL', 'PENDING_BED', 'IN_PROGRESS', 'DISCHARGE_PLANNED'];

const ARRIVAL_CONSENTS: [ConsentType, string][] = [
  ['GENERAL_ADMISSION', 'Ingreso general'],
  ['DATA_PROCESSING', 'Datos personales'],
  ['PROCEDURE', 'Procedimiento'],
];

/** La orden medica programada se registra antes de que el paciente llegue: el contacto y el
 * consentimiento de ingreso se toman al internarlo en la cama. */
function needsArrival(admission: AdmissionDashboardRead | undefined) {
  if (!admission) return false;
  const signed = admission.consents?.some((consent) => consent.consent_type === 'GENERAL_ADMISSION');
  return !admission.responsible_contact_name || !admission.responsible_contact_phone || !signed;
}

export function BedManagementCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getDefault();
  const bedApi = getBedWorkflow();
  const queryClient = useQueryClient();
  const [reserveOpen, setReserveOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  /** Cama a confirmar mientras se toman el contacto y los consentimientos. */
  const [arrivalBedId, setArrivalBedId] = useState<string | null>(null);
  const [selectedBedId, setSelectedBedId] = useState('');
  const [expiresInMinutes, setExpiresInMinutes] = useState(120);
  const [transferBedId, setTransferBedId] = useState('');
  const [transferServiceId, setTransferServiceId] = useState('');
  const [transferReason, setTransferReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const bedsQuery = useQuery({ queryKey: ['beds'], queryFn: () => api.listBedsApiV1BedsGet() });
  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => api.listServicesApiV1ServicesGet(),
  });
  const availableQuery = useQuery({
    queryKey: ['beds-available', hosp.facility_id ?? 'all'],
    queryFn: () =>
      bedApi.searchAvailableBedsApiV1BedsAvailableGet(
        hosp.facility_id ? { facility_id: hosp.facility_id } : undefined,
      ),
  });
  const assignmentsQuery = useQuery({
    queryKey: ['hospitalization-bed-assignments', hosp.id],
    queryFn: () =>
      api.listHospitalizationBedAssignmentsApiV1HospitalizationsHospitalizationIdBedAssignmentsGet(
        hosp.id,
      ),
  });
  const reservationsQuery = useQuery({
    queryKey: ['bed-reservations', hosp.id],
    queryFn: () =>
      bedApi.listBedReservationsApiV1HospitalizationsHospitalizationIdBedReservationsGet(hosp.id),
  });

  const admissionsQuery = useQuery({
    queryKey: ['admissions', hosp.id],
    queryFn: () => api.listAdmissionsApiV1AdmissionsGet({ hospitalization_id: hosp.id }),
  });
  const admission = admissionsQuery.data?.[0];

  const onSettled = () => invalidateHospitalization(queryClient, hosp.id);

  const reserveMutation = useMutation({
    mutationFn: (bedId: string) =>
      bedApi.reserveBedApiV1HospitalizationsHospitalizationIdBedReservationsPost(hosp.id, {
        bed_id: bedId,
        expires_in_minutes: expiresInMinutes,
      }),
    onSuccess: () => {
      onSettled();
      setReserveOpen(false);
      setSelectedBedId('');
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo reservar la cama.')),
  });

  const cancelMutation = useMutation({
    mutationFn: (reservationId: string) =>
      bedApi.cancelBedReservationApiV1BedReservationsReservationIdCancelPost(reservationId, {}),
    onSuccess: () => {
      onSettled();
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo cancelar la reserva.')),
  });

  const assignMutation = useMutation({
    mutationFn: ({ bedId, arrival }: { bedId: string; arrival?: AdmissionArrivalCreate }) =>
      api.assignBedApiV1HospitalizationsHospitalizationIdBedAssignmentsPost(hosp.id, {
        bed_id: bedId,
        arrival: arrival ?? null,
      }),
    onSuccess: () => {
      onSettled();
      setSelectedBedId('');
      setArrivalBedId(null);
      setReserveOpen(false);
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo confirmar el ingreso.')),
  });

  const transferMutation = useMutation({
    mutationFn: () =>
      api.transferBedApiV1HospitalizationsHospitalizationIdTransfersPost(hosp.id, {
        destination_bed_id: transferBedId,
        service_id: transferServiceId || null,
        reason: transferReason || null,
      }),
    onSuccess: () => {
      onSettled();
      setTransferOpen(false);
      setTransferBedId('');
      setTransferServiceId('');
      setTransferReason('');
      setError(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo trasladar al paciente.')),
  });

  const beds = bedsQuery.data ?? [];
  const bedsById = new Map(beds.map((bed) => [bed.id, bed]));
  const assignments = assignmentsQuery.data ?? [];
  const reservations = reservationsQuery.data ?? [];
  const activeAssignment = assignments.find((assignment) => assignment.ended_at === null) ?? null;
  const activeReservation = reservations.find((item) => item.status === 'ACTIVE') ?? null;
  const currentBed = activeAssignment ? bedsById.get(activeAssignment.bed_id) : undefined;
  const availableBeds = availableQuery.data ?? [];
  const transferBeds = availableBeds.filter((bed) => bed.id !== activeAssignment?.bed_id);
  const isOpen = OPEN_STATUSES.includes(hosp.status);
  const busy =
    reserveMutation.isPending ||
    cancelMutation.isPending ||
    assignMutation.isPending ||
    transferMutation.isPending;

  /** Confirmar el ingreso pide antes lo que la admision dejo pendiente, si falta algo. */
  const confirmAdmission = (bedId: string) => {
    setError(null);
    if (needsArrival(admission)) {
      setReserveOpen(false);
      setArrivalBedId(bedId);
    } else {
      assignMutation.mutate({ bedId });
    }
  };

  const bedLabel = (bed: BedRead | undefined, fallbackId: string) =>
    bed ? `${bed.code} · ${bed.ward} · Hab. ${bed.room}` : `Cama ${fallbackId.slice(0, 8)}`;

  return (
    <Card className="p-6">
      <SectionTitle icon={<BedDouble className="h-5 w-5 text-teal-600" />}>
        Gestion de cama
      </SectionTitle>

      <div className="space-y-4">
        <div className="rounded-lg bg-slate-50 px-4 py-3">
          {currentBed ? (
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-slate-700">{currentBed.code}</p>
                <p className="text-xs text-slate-500">
                  {currentBed.ward} · Hab. {currentBed.room} · desde{' '}
                  {formatDateTime(activeAssignment?.started_at)}
                </p>
              </div>
              <BedStatusBadge status={currentBed.status} />
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              {hosp.physically_departed_at
                ? 'El paciente ya se retiro de la cama.'
                : 'Sin cama ocupada.'}
            </p>
          )}
        </div>

        {activeReservation && <ReservationPanel
          reservation={activeReservation}
          bed={bedsById.get(activeReservation.bed_id)}
          canManage={canManage}
          busy={busy}
          onConfirm={() => confirmAdmission(activeReservation.bed_id)}
          onCancel={() => cancelMutation.mutate(activeReservation.id)}
        />}

        <FormError message={error} />

        {canManage && isOpen && (
          <div className="flex flex-wrap gap-2">
            {!activeAssignment && !activeReservation && (
              <ActionButton
                tone="primary"
                onClick={() => {
                  setError(null);
                  setReserveOpen(true);
                }}
                disabled={busy}
              >
                <CalendarClock className="h-4 w-4" />
                Buscar cama
              </ActionButton>
            )}
            {activeAssignment && (
              <ActionButton
                tone="teal"
                onClick={() => {
                  setError(null);
                  setTransferOpen(true);
                }}
                disabled={busy}
              >
                <ArrowRightLeft className="h-4 w-4" />
                Trasladar
              </ActionButton>
            )}
          </div>
        )}

        <div className="rounded-lg border border-slate-100">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-700">Historial de camas</p>
          </div>
          {assignments.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-400">
              No hay asignaciones de cama registradas.
            </p>
          ) : (
            <div className="divide-y divide-slate-100">
              {assignments.map((assignment) => (
                <div key={assignment.id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-700">
                      {bedLabel(bedsById.get(assignment.bed_id), assignment.bed_id)}
                    </p>
                    <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-500">
                      {assignment.ended_at ? 'Finalizada' : 'Actual'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {formatDateTime(assignment.started_at)} →{' '}
                    {formatDateTime(assignment.ended_at) ?? 'Actualidad'}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {reservations.length > 0 && (
          <div className="rounded-lg border border-slate-100">
            <div className="border-b border-slate-100 px-4 py-3">
              <p className="text-sm font-semibold text-slate-700">Reservas</p>
            </div>
            <div className="divide-y divide-slate-100">
              {reservations.map((reservation) => (
                <div key={reservation.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-700">
                      {bedLabel(bedsById.get(reservation.bed_id), reservation.bed_id)}
                    </p>
                    <p className="text-xs text-slate-400">
                      {formatDateTime(reservation.reserved_at)}
                      {reservation.expires_at
                        ? ` · vence ${formatDateTime(reservation.expires_at)}`
                        : ''}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                      RESERVATION_STATUS_COLORS[reservation.status]
                    }`}
                  >
                    {RESERVATION_STATUS_LABELS[reservation.status]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Modal
        open={reserveOpen}
        onClose={() => setReserveOpen(false)}
        title="Camas libres en todos los centros"
        maxWidth="max-w-2xl"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            Reservar mantiene la cama para este paciente sin ocuparla; confirmar el ingreso la
            marca como ocupada e inicia la internacion.
          </p>
          <Field label="Centro y cama">
            <AvailableBedSelect
              value={selectedBedId}
              onChange={setSelectedBedId}
              emptyLabel="Selecciona una cama..."
              className={inputClass}
            />
          </Field>
          <Field label="Vencimiento de la reserva (minutos)">
            <input
              type="number"
              min={1}
              max={10080}
              value={expiresInMinutes}
              onChange={(e) => setExpiresInMinutes(Number(e.target.value))}
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex flex-wrap justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setReserveOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="teal"
              disabled={!selectedBedId || busy}
              onClick={() => reserveMutation.mutate(selectedBedId)}
            >
              <CalendarClock className="h-4 w-4" />
              {reserveMutation.isPending ? 'Reservando...' : 'Reservar'}
            </ActionButton>
            <ActionButton
              tone="primary"
              disabled={!selectedBedId || busy}
              onClick={() => confirmAdmission(selectedBedId)}
            >
              <LogIn className="h-4 w-4" />
              {assignMutation.isPending ? 'Confirmando...' : 'Confirmar ingreso'}
            </ActionButton>
          </div>
        </div>
      </Modal>

      {arrivalBedId && admission && (
        <ArrivalModal
          admission={admission}
          bedLabel={bedLabel(bedsById.get(arrivalBedId), arrivalBedId)}
          busy={busy}
          error={error}
          onClose={() => setArrivalBedId(null)}
          onSubmit={(arrival) => assignMutation.mutate({ bedId: arrivalBedId, arrival })}
        />
      )}

      <Modal open={transferOpen} onClose={() => setTransferOpen(false)} title="Trasladar paciente">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (transferBedId) transferMutation.mutate();
          }}
        >
          <p className="text-sm text-slate-500">
            El traslado es una sola operacion: si la cama destino no esta disponible el paciente
            conserva la cama actual.
          </p>
          <Field label="Cama destino">
            {transferBeds.length === 0 ? (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
                No hay camas disponibles para trasladar.
              </p>
            ) : (
              <select
                required
                value={transferBedId}
                onChange={(e) => setTransferBedId(e.target.value)}
                className={inputClass}
              >
                <option value="">Selecciona una cama...</option>
                {transferBeds.map((bed) => (
                  <option key={bed.id} value={bed.id}>
                    {bed.code} - {bed.ward} (Hab. {bed.room})
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Nuevo servicio responsable (opcional)">
            <select
              value={transferServiceId}
              onChange={(e) => setTransferServiceId(e.target.value)}
              className={inputClass}
            >
              <option value="">Mantener el servicio actual</option>
              {(servicesQuery.data ?? []).map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Motivo">
            <input
              type="text"
              value={transferReason}
              onChange={(e) => setTransferReason(e.target.value)}
              placeholder="Pase a terapia intensiva"
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={() => setTransferOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={!transferBedId || busy}>
              <ArrowRightLeft className="h-4 w-4" />
              {transferMutation.isPending ? 'Trasladando...' : 'Trasladar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

function ArrivalModal({
  admission,
  bedLabel,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  admission: AdmissionDashboardRead;
  bedLabel: string;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (arrival: AdmissionArrivalCreate) => void;
}) {
  const alreadySigned = new Set((admission.consents ?? []).map((consent) => consent.consent_type));
  const [contact, setContact] = useState({
    name: admission.responsible_contact_name ?? '',
    phone: admission.responsible_contact_phone ?? '',
    relationship: admission.responsible_contact_relationship ?? '',
  });
  const [consents, setConsents] = useState<ConsentType[]>([]);
  const patientName = `${admission.patient.first_name} ${admission.patient.last_name}`;

  return (
    <Modal open onClose={onClose} title="Ingreso del paciente">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({
            responsible_contact_name: contact.name.trim() || null,
            responsible_contact_phone: contact.phone.trim() || null,
            responsible_contact_relationship: contact.relationship.trim() || null,
            consents: consents.map((consent_type) => ({
              consent_type,
              signed_by: contact.name.trim() || patientName,
            })),
          });
        }}
      >
        <p className="text-sm text-slate-500">
          {patientName} se interna en {bedLabel}. Antes de ocupar la cama se toman el contacto
          responsable y los consentimientos que quedaron pendientes en la admision.
        </p>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Contacto responsable">
            <input
              required
              value={contact.name}
              onChange={(e) => setContact({ ...contact, name: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Telefono">
            <input
              required
              value={contact.phone}
              onChange={(e) => setContact({ ...contact, phone: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Vinculo">
            <input
              value={contact.relationship}
              onChange={(e) => setContact({ ...contact, relationship: e.target.value })}
              className={inputClass}
            />
          </Field>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {ARRIVAL_CONSENTS.map(([type, label]) => {
            const signed = alreadySigned.has(type);
            return (
              <label
                key={type}
                className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600"
              >
                <input
                  type="checkbox"
                  disabled={signed}
                  checked={signed || consents.includes(type)}
                  onChange={(e) =>
                    setConsents((current) =>
                      e.target.checked ? [...current, type] : current.filter((item) => item !== type),
                    )
                  }
                  className="h-4 w-4 accent-teal-600"
                />
                {label}
                {signed && <span className="text-xs text-slate-400">(firmado)</span>}
              </label>
            );
          })}
        </div>
        <FormError message={error} />
        <div className="flex justify-end gap-3 pt-2">
          <ActionButton tone="neutral" onClick={onClose}>
            Cancelar
          </ActionButton>
          <ActionButton tone="primary" type="submit" disabled={busy}>
            <LogIn className="h-4 w-4" />
            {busy ? 'Confirmando...' : 'Confirmar ingreso'}
          </ActionButton>
        </div>
      </form>
    </Modal>
  );
}

function ReservationPanel({
  reservation,
  bed,
  canManage,
  busy,
  onConfirm,
  onCancel,
}: {
  reservation: BedReservationRead;
  bed: BedRead | undefined;
  canManage: boolean;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const minutes = minutesUntil(reservation.expires_at);

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-amber-800">
            Cama reservada: {bed ? `${bed.code} · Hab. ${bed.room}` : reservation.bed_id.slice(0, 8)}
          </p>
          <p className="text-xs text-amber-700">
            {reservation.expires_at
              ? minutes !== null && minutes > 0
                ? `Vence en ${minutes} min (${formatDateTime(reservation.expires_at)})`
                : `Vencida el ${formatDateTime(reservation.expires_at)}`
              : 'Sin vencimiento'}
          </p>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <ActionButton tone="primary" onClick={onConfirm} disabled={busy}>
              <LogIn className="h-4 w-4" />
              Confirmar ingreso
            </ActionButton>
            <ActionButton tone="danger" onClick={onCancel} disabled={busy}>
              <XCircle className="h-4 w-4" />
              Cancelar reserva
            </ActionButton>
          </div>
        )}
      </div>
    </div>
  );
}

export default BedManagementCard;
