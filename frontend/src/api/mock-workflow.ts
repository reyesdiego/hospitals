/**
 * Mock handlers for the hospitalization workflow (bed reservations, cleaning, service
 * history, care team, discharge lifecycle and audit trail).
 *
 * They mirror the rules the API enforces: reservation and occupancy are different, the
 * clinical discharge does not release the bed, and the administrative discharge needs the
 * patient to have physically left.
 */
import type {
  BedRead,
  BedReservationRead,
  BedStatus,
  BedStatusHistoryRead,
  CareTeamMemberRead,
  DischargePlanRead,
  DischargeRead,
  HospitalizationEventRead,
  HospitalizationEventType,
  HospitalizationRead,
  ServiceAssignmentRead,
} from './model';
import { type MockDB, now, saveDB, uuid } from './mock-db';

type Ok = { kind: 'ok'; data: unknown; status: number };
type Err = { kind: 'error'; status: number; detail: string };
export type WorkflowResult = Ok | Err;

const ok = (data: unknown, status = 200): Ok => ({ kind: 'ok', data, status });
const err = (status: number, detail: string): Err => ({ kind: 'error', status, detail });

const OPEN_STATUSES = ['PENDING_BED', 'IN_PROGRESS', 'DISCHARGE_PLANNED'];
const CLINICALLY_ACTIVE = ['IN_PROGRESS', 'DISCHARGE_PLANNED'];
const OPERATIONAL_STATUSES: BedStatus[] = [
  'AVAILABLE',
  'PENDING_CLEANING',
  'CLEANING',
  'BLOCKED',
  'MAINTENANCE',
  'OUT_OF_SERVICE',
];

export function recordEvent(
  db: MockDB,
  eventType: HospitalizationEventType,
  fields: Partial<Omit<HospitalizationEventRead, 'id' | 'event_type'>> = {},
): HospitalizationEventRead {
  const event: HospitalizationEventRead = {
    id: uuid(),
    event_type: eventType,
    hospitalization_id: fields.hospitalization_id ?? null,
    admission_id: fields.admission_id ?? null,
    bed_id: fields.bed_id ?? null,
    patient_id: fields.patient_id ?? null,
    occurred_at: fields.occurred_at ?? now(),
    actor: fields.actor ?? null,
    details: fields.details ?? null,
  };
  db.events.push(event);
  return event;
}

export function recordBedStatus(
  db: MockDB,
  bed: BedRead,
  status: BedStatus,
  changedBy: string | null = null,
  reason: string | null = null,
): BedStatusHistoryRead {
  const entry: BedStatusHistoryRead = {
    id: uuid(),
    bed_id: bed.id,
    previous_status: bed.status,
    new_status: status,
    changed_at: now(),
    changed_by: changedBy,
    reason,
  };
  db.bedStatusHistory.push(entry);
  bed.status = status;
  if (status !== 'OCCUPIED') bed.patient = null;
  if (status !== 'RESERVED') {
    bed.reserved_for = null;
    bed.reservation_expires_at = null;
  }
  return entry;
}

/** Confirms the hold of a bed when the patient physically occupies it. */
export function completeReservationForBed(
  db: MockDB,
  bedId: string,
  hospitalizationId: string,
): BedReservationRead | null {
  const reservation = db.bedReservations.find(
    (item) => item.bed_id === bedId && item.status === 'ACTIVE',
  );
  if (!reservation) return null;
  if (reservation.hospitalization_id !== hospitalizationId) return reservation;
  reservation.status = 'COMPLETED';
  reservation.completed_at = now();
  return reservation;
}

function activeAssignment(db: MockDB, hospitalizationId: string) {
  return db.bedAssignments.find(
    (item) => item.hospitalization_id === hospitalizationId && item.ended_at === null,
  );
}

function activeAssignmentForBed(db: MockDB, bedId: string) {
  return db.bedAssignments.find((item) => item.bed_id === bedId && item.ended_at === null);
}

function careTeamFor(db: MockDB, hospitalizationId: string) {
  return db.careTeams.find((item) => item.hospitalization_id === hospitalizationId);
}

function expireDueReservations(db: MockDB): BedReservationRead[] {
  const expired = db.bedReservations.filter(
    (item) =>
      item.status === 'ACTIVE' && item.expires_at !== null && new Date(item.expires_at) <= new Date(),
  );
  expired.forEach((reservation) => {
    reservation.status = 'EXPIRED';
    const bed = db.beds.find((item) => item.id === reservation.bed_id);
    if (bed && bed.status === 'RESERVED') {
      recordBedStatus(db, bed, 'AVAILABLE', null, 'Reserva vencida');
    }
    recordEvent(db, 'BED_RESERVATION_EXPIRED', {
      hospitalization_id: reservation.hospitalization_id,
      bed_id: reservation.bed_id,
    });
  });
  return expired;
}

export function handleWorkflowRequest(
  db: MockDB,
  url: string,
  method: string,
  body: Record<string, unknown>,
): WorkflowResult | null {
  const match = (pattern: RegExp) => url.match(pattern);
  const text = (value: unknown) => (typeof value === 'string' && value ? value : null);

  // ----------------------------------------------------------------- beds
  if (url.startsWith('/api/v1/beds/available') && method === 'get') {
    expireDueReservations(db);
    saveDB(db);
    const available = db.beds.filter(
      (bed) =>
        bed.status === 'AVAILABLE' &&
        !activeAssignmentForBed(db, bed.id) &&
        !db.bedReservations.some((item) => item.bed_id === bed.id && item.status === 'ACTIVE'),
    );
    return ok(available);
  }

  const historyMatch = match(/^\/api\/v1\/beds\/([^/]+)\/status-history$/);
  if (historyMatch && method === 'get') {
    const bedId = historyMatch[1];
    if (!db.beds.some((bed) => bed.id === bedId)) return err(404, 'Cama inexistente');
    const history = db.bedStatusHistory
      .filter((entry) => entry.bed_id === bedId)
      .sort((a, b) => b.changed_at.localeCompare(a.changed_at));
    return ok(history);
  }

  const cleaningMatch = match(/^\/api\/v1\/beds\/([^/]+)\/cleaning\/(start|complete)$/);
  if (cleaningMatch && method === 'post') {
    const bed = db.beds.find((item) => item.id === cleaningMatch[1]);
    if (!bed) return err(404, 'Cama inexistente');
    const changedBy = text(body.changed_by);
    const reason = text(body.reason);
    if (cleaningMatch[2] === 'start') {
      if (bed.status !== 'PENDING_CLEANING') {
        return err(409, 'La cama no está pendiente de limpieza');
      }
      recordBedStatus(db, bed, 'CLEANING', changedBy, reason);
      recordEvent(db, 'BED_CLEANING_STARTED', { bed_id: bed.id, actor: changedBy });
    } else {
      if (bed.status !== 'CLEANING' && bed.status !== 'PENDING_CLEANING') {
        return err(409, 'La cama no está en proceso de limpieza');
      }
      recordBedStatus(db, bed, 'AVAILABLE', changedBy, reason);
      recordEvent(db, 'BED_AVAILABLE', { bed_id: bed.id, actor: changedBy });
    }
    saveDB(db);
    return ok(bed);
  }

  const statusMatch = match(/^\/api\/v1\/beds\/([^/]+)\/status$/);
  if (statusMatch && method === 'post') {
    const bed = db.beds.find((item) => item.id === statusMatch[1]);
    if (!bed) return err(404, 'Cama inexistente');
    const status = body.status as BedStatus;
    if (!OPERATIONAL_STATUSES.includes(status)) {
      return err(409, 'La ocupación y la reserva se gestionan desde la internación');
    }
    if (activeAssignmentForBed(db, bed.id)) {
      return err(409, 'La cama está ocupada por una internación');
    }
    if (db.bedReservations.some((item) => item.bed_id === bed.id && item.status === 'ACTIVE')) {
      return err(409, 'La cama tiene una reserva activa');
    }
    if (bed.status !== status) {
      recordBedStatus(db, bed, status, text(body.changed_by), text(body.reason));
    }
    saveDB(db);
    return ok(bed);
  }

  // --------------------------------------------------------- reservations
  const reservationsMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/bed-reservations$/);
  if (reservationsMatch && method === 'get') {
    const reservations = db.bedReservations
      .filter((item) => item.hospitalization_id === reservationsMatch[1])
      .sort((a, b) => b.reserved_at.localeCompare(a.reserved_at));
    return ok(reservations);
  }
  if (reservationsMatch && method === 'post') {
    const hospitalizationId = reservationsMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (!OPEN_STATUSES.includes(hospitalization.status)) {
      return err(409, 'La internación no está activa');
    }
    const bed = db.beds.find((item) => item.id === body.bed_id);
    if (!bed) return err(404, 'Cama inexistente');
    expireDueReservations(db);
    if (bed.status !== 'AVAILABLE') return err(409, 'La cama no está disponible');
    if (activeAssignmentForBed(db, bed.id)) {
      return err(409, 'La cama está ocupada por una internación');
    }
    if (
      db.bedReservations.some(
        (item) => item.hospitalization_id === hospitalizationId && item.status === 'ACTIVE',
      )
    ) {
      return err(409, 'La internación ya tiene una reserva activa');
    }
    if (activeAssignment(db, hospitalizationId)) {
      return err(409, 'La internación ya tiene una cama asignada');
    }

    const minutes = typeof body.expires_in_minutes === 'number' ? body.expires_in_minutes : null;
    const reservedAt = now();
    const reservation: BedReservationRead = {
      id: uuid(),
      hospitalization_id: hospitalizationId,
      bed_id: bed.id,
      status: 'ACTIVE',
      reserved_at: reservedAt,
      expires_at: minutes
        ? new Date(new Date(reservedAt).getTime() + minutes * 60000).toISOString()
        : null,
      reserved_by: text(body.reserved_by),
      completed_at: null,
      cancelled_at: null,
      reason: text(body.reason),
    };
    db.bedReservations.push(reservation);
    recordBedStatus(db, bed, 'RESERVED', reservation.reserved_by, reservation.reason);
    bed.reserved_for = db.patients.find((item) => item.id === hospitalization.patient_id) ?? null;
    bed.reservation_expires_at = reservation.expires_at;
    recordEvent(db, 'BED_RESERVED', {
      hospitalization_id: hospitalizationId,
      bed_id: bed.id,
      patient_id: hospitalization.patient_id,
      actor: reservation.reserved_by,
    });
    saveDB(db);
    return ok(reservation, 201);
  }

  if (url === '/api/v1/bed-reservations/expire-due' && method === 'post') {
    const expired = expireDueReservations(db);
    saveDB(db);
    return ok(expired);
  }

  const cancelMatch = match(/^\/api\/v1\/bed-reservations\/([^/]+)\/cancel$/);
  if (cancelMatch && method === 'post') {
    const reservation = db.bedReservations.find((item) => item.id === cancelMatch[1]);
    if (!reservation) return err(404, 'Reserva inexistente');
    if (reservation.status !== 'ACTIVE') return err(409, 'La reserva no está activa');
    reservation.status = 'CANCELLED';
    reservation.cancelled_at = now();
    const bed = db.beds.find((item) => item.id === reservation.bed_id);
    if (bed && bed.status === 'RESERVED') {
      recordBedStatus(db, bed, 'AVAILABLE', text(body.cancelled_by), text(body.reason));
    }
    recordEvent(db, 'BED_RESERVATION_CANCELLED', {
      hospitalization_id: reservation.hospitalization_id,
      bed_id: reservation.bed_id,
      actor: text(body.cancelled_by),
    });
    saveDB(db);
    return ok(reservation);
  }

  // ------------------------------------------------- admission provenance
  const admissionMatch = match(/^\/api\/v1\/admissions\/([^/]+)$/);
  if (admissionMatch && method === 'get') {
    const admission = db.admissions.find((item) => item.id === admissionMatch[1]);
    return admission ? ok(admission) : err(404, 'Admisión inexistente');
  }

  const authorizationsMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/authorizations$/);
  if (authorizationsMatch && method === 'get') {
    const authorizations = db.authorizations
      .filter((item) => item.hospitalization_id === authorizationsMatch[1])
      .sort((a, b) => b.requested_at.localeCompare(a.requested_at));
    return ok(authorizations);
  }

  const admissionAuthorizationsMatch = match(/^\/api\/v1\/admissions\/([^/]+)\/authorizations$/);
  if (admissionAuthorizationsMatch && method === 'get') {
    const authorizations = db.authorizations
      .filter((item) => item.admission_id === admissionAuthorizationsMatch[1])
      .sort((a, b) => b.requested_at.localeCompare(a.requested_at));
    return ok(authorizations);
  }

  if (url === '/api/v1/hospitalizations' && method === 'post') {
    // An inpatient process cannot exist without the request that justifies it.
    const admission = db.admissions.find((item) => item.id === body.admission_id);
    if (!admission) return err(404, 'Admisión inexistente');
    if (admission.hospitalization_id) {
      return err(409, 'La solicitud de admisión ya tiene una internación');
    }
    if (
      admission.status === 'REJECTED' ||
      admission.status === 'CANCELLED' ||
      admission.status === 'ADMINISTRATIVE_DISCHARGE'
    ) {
      return err(409, 'La solicitud de admisión no está vigente');
    }
    if (admission.authorization_status === 'PENDING') {
      return err(409, 'La autorización está pendiente');
    }

    const at = now();
    const hospitalization: HospitalizationRead = {
      id: uuid(),
      patient_id: admission.patient_id,
      episode_id: admission.episode_id ?? null,
      facility_id: text(body.facility_id) ?? admission.facility_id ?? null,
      admission_type: admission.admission_type,
      status: 'PENDING_BED',
      admission_reason: admission.admission_reason,
      admitted_at: null,
      clinically_discharged_at: null,
      physically_departed_at: null,
      administratively_discharged_at: null,
      closed_at: null,
    };
    db.hospitalizations.push(hospitalization);
    db.careTeams.push({ id: uuid(), hospitalization_id: hospitalization.id, members: [] });
    const serviceId = text(body.responsible_service_id) ?? admission.requesting_service_id;
    if (serviceId) {
      db.serviceAssignments.push({
        id: uuid(),
        hospitalization_id: hospitalization.id,
        service_id: serviceId,
        started_at: at,
        ended_at: null,
        reason: 'Servicio responsable inicial',
        assigned_by: null,
      });
    }
    admission.hospitalization_id = hospitalization.id;
    if (admission.status === 'PRE_ADMITTED') admission.status = 'PENDING_BED';
    recordEvent(db, 'HOSPITALIZATION_CREATED', {
      hospitalization_id: hospitalization.id,
      admission_id: admission.id,
      patient_id: admission.patient_id,
      occurred_at: at,
    });
    saveDB(db);
    return ok(hospitalization, 201);
  }

  // ------------------------------------------------------ hospitalization
  const hospitalizationMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)$/);
  if (hospitalizationMatch && method === 'get') {
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationMatch[1]);
    return hospitalization ? ok(hospitalization) : err(404, 'Internación inexistente');
  }

  const eventsMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/events$/);
  if (eventsMatch && method === 'get') {
    const events = db.events
      .filter((event) => event.hospitalization_id === eventsMatch[1])
      .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
    return ok(events);
  }

  const servicesMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/service-assignments$/);
  if (servicesMatch && method === 'get') {
    const assignments = db.serviceAssignments
      .filter((item) => item.hospitalization_id === servicesMatch[1])
      .sort((a, b) => b.started_at.localeCompare(a.started_at));
    return ok(assignments);
  }
  if (servicesMatch && method === 'post') {
    const hospitalizationId = servicesMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (!OPEN_STATUSES.includes(hospitalization.status)) {
      return err(409, 'La internación no está activa');
    }
    const serviceId = String(body.service_id ?? '');
    if (!db.services.some((service) => service.id === serviceId)) {
      return err(404, 'Servicio inexistente');
    }
    const current = db.serviceAssignments.find(
      (item) => item.hospitalization_id === hospitalizationId && item.ended_at === null,
    );
    if (current?.service_id === serviceId) {
      return err(409, 'El servicio ya es el responsable actual');
    }
    const at = now();
    if (current) current.ended_at = at;
    const assignment: ServiceAssignmentRead = {
      id: uuid(),
      hospitalization_id: hospitalizationId,
      service_id: serviceId,
      started_at: at,
      ended_at: null,
      reason: text(body.reason),
      assigned_by: text(body.assigned_by),
    };
    db.serviceAssignments.push(assignment);
    recordEvent(db, 'SERVICE_ASSIGNED', {
      hospitalization_id: hospitalizationId,
      patient_id: hospitalization.patient_id,
      occurred_at: at,
    });
    saveDB(db);
    return ok(assignment, 201);
  }

  // ------------------------------------------------------------ care team
  const careTeamMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/care-team$/);
  if (careTeamMatch && method === 'get') {
    const careTeam = careTeamFor(db, careTeamMatch[1]);
    return careTeam ? ok(careTeam) : err(404, 'La internación no tiene equipo asistencial');
  }

  const membersMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/care-team\/members$/);
  if (membersMatch && method === 'post') {
    const hospitalizationId = membersMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (!OPEN_STATUSES.includes(hospitalization.status)) {
      return err(409, 'La internación no está activa');
    }
    const practitionerId = String(body.practitioner_id ?? '');
    if (!db.professionals.some((item) => item.id === practitionerId)) {
      return err(404, 'Profesional inexistente');
    }
    let careTeam = careTeamFor(db, hospitalizationId);
    if (!careTeam) {
      careTeam = { id: uuid(), hospitalization_id: hospitalizationId, members: [] };
      db.careTeams.push(careTeam);
    }
    const role = body.role as CareTeamMemberRead['role'];
    if (
      (careTeam.members ?? []).some(
        (member) =>
          member.ended_at === null &&
          member.practitioner_id === practitionerId &&
          member.role === role,
      )
    ) {
      return err(409, 'El profesional ya cumple ese rol en el equipo asistencial');
    }
    if (
      role === 'ATTENDING_PHYSICIAN' &&
      (careTeam.members ?? []).some(
        (member) => member.ended_at === null && member.role === 'ATTENDING_PHYSICIAN',
      )
    ) {
      return err(409, 'El profesional ya cumple ese rol en el equipo asistencial');
    }
    const member: CareTeamMemberRead = {
      id: uuid(),
      care_team_id: careTeam.id,
      practitioner_id: practitionerId,
      role,
      started_at: now(),
      ended_at: null,
      notes: text(body.notes),
    };
    careTeam.members = [...(careTeam.members ?? []), member];
    recordEvent(db, 'CARE_TEAM_MEMBER_ASSIGNED', {
      hospitalization_id: hospitalizationId,
      patient_id: hospitalization.patient_id,
    });
    saveDB(db);
    return ok(member, 201);
  }

  const endMemberMatch = match(
    /^\/api\/v1\/hospitalizations\/([^/]+)\/care-team\/members\/([^/]+)\/end$/,
  );
  if (endMemberMatch && method === 'post') {
    const careTeam = careTeamFor(db, endMemberMatch[1]);
    if (!careTeam) return err(404, 'La internación no tiene equipo asistencial');
    const member = (careTeam.members ?? []).find((item) => item.id === endMemberMatch[2]);
    if (!member) return err(404, 'Integrante inexistente');
    if (member.ended_at === null) {
      member.ended_at = now();
      recordEvent(db, 'CARE_TEAM_MEMBER_ENDED', { hospitalization_id: endMemberMatch[1] });
      saveDB(db);
    }
    return ok(member);
  }

  // ------------------------------------------------------------- discharge
  const plansMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/discharge-plans$/);
  if (plansMatch && method === 'get') {
    const plans = db.dischargePlans
      .filter((item) => item.hospitalization_id === plansMatch[1])
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    return ok(plans);
  }
  if (plansMatch && method === 'post') {
    const hospitalizationId = plansMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (!CLINICALLY_ACTIVE.includes(hospitalization.status)) {
      return err(409, 'La internación no está en curso');
    }
    if (
      db.dischargePlans.some(
        (item) =>
          item.hospitalization_id === hospitalizationId &&
          (item.status === 'PLANNED' || item.status === 'CONFIRMED'),
      )
    ) {
      return err(409, 'La internación ya tiene un plan de alta activo');
    }
    const plan: DischargePlanRead = {
      id: uuid(),
      hospitalization_id: hospitalizationId,
      planned_date: text(body.planned_date),
      destination: (body.destination as DischargePlanRead['destination']) ?? 'HOME',
      requires_transport: Boolean(body.requires_transport),
      requires_home_care: Boolean(body.requires_home_care),
      status: (body.status as DischargePlanRead['status']) ?? 'PLANNED',
      created_by: text(body.created_by),
      notes: text(body.notes),
      created_at: now(),
    };
    db.dischargePlans.push(plan);
    // Planning the discharge neither releases the bed nor ends the hospitalization.
    if (plan.status === 'PLANNED' || plan.status === 'CONFIRMED') {
      hospitalization.status = 'DISCHARGE_PLANNED';
    }
    recordEvent(db, 'DISCHARGE_PLANNED', {
      hospitalization_id: hospitalizationId,
      patient_id: hospitalization.patient_id,
      actor: plan.created_by,
    });
    saveDB(db);
    return ok(plan, 201);
  }

  const dischargeMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/discharge$/);
  if (dischargeMatch && method === 'get') {
    const discharge = db.discharges.find((item) => item.hospitalization_id === dischargeMatch[1]);
    return discharge ? ok(discharge) : err(404, 'La internación no tiene alta clínica');
  }

  const clinicalMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/clinical-discharge$/);
  if (clinicalMatch && method === 'post') {
    const hospitalizationId = clinicalMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (!CLINICALLY_ACTIVE.includes(hospitalization.status)) {
      return err(409, 'La internación debe estar en curso para registrar el alta clínica');
    }
    const at = text(body.effective_at) ?? now();
    const discharge: DischargeRead = {
      id: uuid(),
      hospitalization_id: hospitalizationId,
      discharge_type: (body.discharge_type as DischargeRead['discharge_type']) ?? 'MEDICAL',
      discharge_reason: text(body.discharge_reason),
      destination: (body.destination as DischargeRead['destination']) ?? null,
      ordered_by: text(body.ordered_by),
      ordered_by_practitioner_id: text(body.ordered_by_practitioner_id),
      ordered_at: now(),
      effective_at: at,
      instructions: text(body.instructions),
    };
    db.discharges.push(discharge);
    hospitalization.status = 'CLINICALLY_DISCHARGED';
    hospitalization.clinically_discharged_at = at;
    // The bed stays OCCUPIED: the patient is still in it.
    db.dischargePlans
      .filter(
        (item) =>
          item.hospitalization_id === hospitalizationId &&
          (item.status === 'PLANNED' || item.status === 'CONFIRMED'),
      )
      .forEach((item) => {
        item.status = 'COMPLETED';
      });
    recordEvent(db, 'CLINICAL_DISCHARGE_COMPLETED', {
      hospitalization_id: hospitalizationId,
      patient_id: hospitalization.patient_id,
      occurred_at: at,
    });
    saveDB(db);
    return ok(discharge, 201);
  }

  const departureMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/physical-departure$/);
  if (departureMatch && method === 'post') {
    const hospitalizationId = departureMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (!hospitalization.clinically_discharged_at) {
      return err(409, 'La salida física requiere el alta clínica previa');
    }
    if (hospitalization.physically_departed_at) {
      return err(409, 'La salida física ya fue registrada');
    }
    const assignment = activeAssignment(db, hospitalizationId);
    if (!assignment) return err(404, 'La internación no tiene una cama activa');

    const at = text(body.departed_at) ?? now();
    assignment.ended_at = at;
    assignment.ended_by = text(body.released_by);
    hospitalization.physically_departed_at = at;
    const bed = db.beds.find((item) => item.id === assignment.bed_id);
    if (bed) {
      recordBedStatus(db, bed, 'PENDING_CLEANING', text(body.released_by), text(body.notes));
      recordEvent(db, 'BED_RELEASED', {
        hospitalization_id: hospitalizationId,
        bed_id: bed.id,
        occurred_at: at,
      });
    }
    recordEvent(db, 'PATIENT_PHYSICALLY_DEPARTED', {
      hospitalization_id: hospitalizationId,
      bed_id: assignment.bed_id,
      patient_id: hospitalization.patient_id,
      actor: text(body.released_by),
      occurred_at: at,
    });
    saveDB(db);
    return ok(hospitalization);
  }

  const administrativeMatch = match(
    /^\/api\/v1\/hospitalizations\/([^/]+)\/administrative-discharge$/,
  );
  if (administrativeMatch && method === 'post') {
    const hospitalizationId = administrativeMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (
      hospitalization.status === 'ADMINISTRATIVELY_DISCHARGED' ||
      hospitalization.status === 'CLOSED'
    ) {
      return ok(hospitalization);
    }
    if (!hospitalization.clinically_discharged_at) {
      return err(409, 'El alta administrativa requiere el alta clínica previa');
    }
    if (!hospitalization.physically_departed_at) {
      return err(409, 'El alta administrativa requiere la salida física del paciente');
    }
    const at = now();
    hospitalization.status = 'ADMINISTRATIVELY_DISCHARGED';
    hospitalization.administratively_discharged_at = at;
    db.serviceAssignments
      .filter((item) => item.hospitalization_id === hospitalizationId && item.ended_at === null)
      .forEach((item) => {
        item.ended_at = at;
      });
    const careTeam = careTeamFor(db, hospitalizationId);
    (careTeam?.members ?? [])
      .filter((member) => member.ended_at === null)
      .forEach((member) => {
        member.ended_at = at;
      });
    const admission = db.admissions.find((item) => item.hospitalization_id === hospitalizationId);
    if (admission) {
      admission.status = 'ADMINISTRATIVE_DISCHARGE';
      admission.administrative_discharged_at = at;
      if (admission.episode) {
        admission.episode.status = 'CLOSED';
        admission.episode.closed_at = at;
      }
      if (text(body.notes)) admission.notes = text(body.notes);
    }
    recordEvent(db, 'ADMINISTRATIVE_DISCHARGE_COMPLETED', {
      hospitalization_id: hospitalizationId,
      admission_id: admission?.id ?? null,
      patient_id: hospitalization.patient_id,
      actor: text(body.actor),
      occurred_at: at,
    });
    saveDB(db);
    return ok(hospitalization);
  }

  // ------------------------------------------------------------- transfers
  const transfersMatch = match(/^\/api\/v1\/hospitalizations\/([^/]+)\/transfers$/);
  if (transfersMatch && method === 'post') {
    const hospitalizationId = transfersMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    if (!OPEN_STATUSES.includes(hospitalization.status)) {
      return err(409, 'La internación no está activa');
    }
    const assignment = activeAssignment(db, hospitalizationId);
    if (!assignment) return err(404, 'La internación no tiene una cama activa');
    const destinationId = String(body.destination_bed_id ?? '');
    if (assignment.bed_id === destinationId) {
      return err(409, 'La transferencia no puede apuntar a la misma cama');
    }
    const destination = db.beds.find((item) => item.id === destinationId);
    if (!destination) return err(404, 'Cama destino inexistente');
    const reservation = db.bedReservations.find(
      (item) => item.bed_id === destinationId && item.status === 'ACTIVE',
    );
    const reservedForThisStay = reservation?.hospitalization_id === hospitalizationId;
    if (destination.status !== 'AVAILABLE' && !reservedForThisStay) {
      return err(409, 'La cama destino no está disponible');
    }
    if (activeAssignmentForBed(db, destinationId)) {
      return err(409, 'La cama destino no está disponible');
    }

    const at = now();
    const reason = text(body.reason);
    const completedBy = text(body.completed_by);
    if (reservedForThisStay) completeReservationForBed(db, destinationId, hospitalizationId);
    assignment.ended_at = at;
    assignment.ended_by = completedBy;
    const source = db.beds.find((item) => item.id === assignment.bed_id);
    if (source) recordBedStatus(db, source, 'PENDING_CLEANING', completedBy, reason);

    db.bedAssignments.push({
      id: uuid(),
      hospitalization_id: hospitalizationId,
      bed_id: destinationId,
      started_at: at,
      ended_at: null,
      assignment_reason: reason,
      assigned_by: completedBy,
      ended_by: null,
    });
    recordBedStatus(db, destination, 'OCCUPIED', completedBy, reason);
    destination.patient =
      db.patients.find((item) => item.id === hospitalization.patient_id) ?? null;

    const serviceId = text(body.service_id);
    if (serviceId) {
      const current = db.serviceAssignments.find(
        (item) => item.hospitalization_id === hospitalizationId && item.ended_at === null,
      );
      if (current && current.service_id !== serviceId) {
        current.ended_at = at;
        db.serviceAssignments.push({
          id: uuid(),
          hospitalization_id: hospitalizationId,
          service_id: serviceId,
          started_at: at,
          ended_at: null,
          reason,
          assigned_by: completedBy,
        });
        recordEvent(db, 'SERVICE_ASSIGNED', {
          hospitalization_id: hospitalizationId,
          occurred_at: at,
        });
      }
    }
    recordEvent(db, 'PATIENT_TRANSFERRED', {
      hospitalization_id: hospitalizationId,
      bed_id: destinationId,
      patient_id: hospitalization.patient_id,
      actor: completedBy,
      occurred_at: at,
    });
    saveDB(db);
    return ok(
      {
        id: uuid(),
        hospitalization_id: hospitalizationId,
        from_bed_id: source?.id ?? assignment.bed_id,
        to_bed_id: destinationId,
        status: 'COMPLETED',
        requested_at: at,
        completed_at: at,
        cancelled_at: null,
        reason,
      },
      201,
    );
  }

  // --------------------------------------------------------- professionals
  if (url === '/api/v1/professionals' && method === 'get') {
    return ok(db.professionals);
  }
  if (url === '/api/v1/specialties' && method === 'get') {
    return ok(db.specialties);
  }

  return null;
}
