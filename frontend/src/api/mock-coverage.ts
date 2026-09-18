/**
 * Mock handlers for the coverage catalog: financiadores, their planes and the coberturas a
 * patient holds under them.
 *
 * They mirror the API rules: the payer code is unique, the plan code is unique inside its
 * payer, the plan of a coverage has to belong to the informed payer, a coverage snapshots
 * the payer and plan names every time it is saved, and nothing that is already referenced
 * can be deleted.
 */
import type {
  CoverageStatus,
  HealthPlanPracticeRead,
  MedicalPracticeRead,
  HealthPlanRead,
  PatientCoverageRead,
  PayerRead,
} from './model';
import { type MockDB, now, saveDB, uuid } from './mock-db';

type Ok = { kind: 'ok'; data: unknown; status: number };
export type CoverageError = { kind: 'error'; status: number; detail: string };
type Err = CoverageError;
export type CoverageResult = Ok | Err;

const ok = (data: unknown, status = 200): Ok => ({ kind: 'ok', data, status });
const err = (status: number, detail: string): Err => ({ kind: 'error', status, detail });

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() !== '' ? value : null;

/** Same rules as ``coverage_fields`` in the API. */
export function coverageFields(
  db: MockDB,
  body: Record<string, unknown>,
): CoverageError | Omit<PatientCoverageRead, 'id' | 'patient_id' | 'created_at'> {
  const payerId = text(body.payer_id);
  const planId = text(body.health_plan_id);
  let payerName = text(body.payer_name);
  let planName = text(body.plan_name);

  let payer = payerId ? db.payers.find((item) => item.id === payerId) : undefined;
  if (payerId && !payer) return err(404, 'Financiador inexistente');
  if (payer) payerName = payer.name;

  if (planId) {
    const plan = db.healthPlans.find((item) => item.id === planId);
    if (!plan) return err(404, 'Plan inexistente');
    if (payerId && plan.payer_id !== payerId) {
      return err(422, 'El plan no pertenece al financiador informado');
    }
    if (!payer) {
      payer = db.payers.find((item) => item.id === plan.payer_id);
      payerName = payer?.name ?? payerName;
    }
    planName = plan.name;
  }
  if (!payerName) return err(422, 'Informe payer_id o payer_name');

  const validFrom = text(body.valid_from);
  const validUntil = text(body.valid_until);
  if (validFrom && validUntil && validUntil < validFrom) {
    return err(422, 'La vigencia de la cobertura es inválida');
  }

  return {
    payer_id: payerId ?? payer?.id ?? null,
    health_plan_id: planId,
    payer_name: payerName,
    plan_name: planName,
    member_number: text(body.member_number),
    authorization_required: body.authorization_required === true,
    valid_from: validFrom,
    valid_until: validUntil,
    status: (text(body.status) as CoverageStatus) ?? 'ACTIVE',
  };
}

export function isCoverageError(
  value: CoverageError | Omit<PatientCoverageRead, 'id' | 'patient_id' | 'created_at'>,
): value is CoverageError {
  return 'kind' in value;
}

/** ``No se puede eliminar ... porque está en uso: X, Y``, like the API. */
function blockedBy(prefix: string, counts: Record<string, number>): Err | null {
  const used = Object.entries(counts)
    .filter(([, total]) => total > 0)
    .map(([label]) => label);
  return used.length ? err(409, `${prefix}: ${used.join(', ')}`) : null;
}

const decimal = (value: unknown): string | null => {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed.toFixed(2);
};

/** Carencia vacía en el plan significa que rige la de la práctica. */
function waitingPeriodOf(body: Record<string, unknown>): number | null {
  const value = body.waiting_period_days;
  if (value === null || value === undefined || value === '') return null;
  return Number(value);
}

/** Flattens the practice into the row, like ``health_plan_practice_read`` in the API. */
function planPracticeFrom(
  planId: string,
  practice: MedicalPracticeRead,
  body: Record<string, unknown>,
): HealthPlanPracticeRead {
  const waiting = waitingPeriodOf(body);
  return {
    id: uuid(),
    health_plan_id: planId,
    practice_id: practice.id,
    practice_code: practice.code,
    practice_name: practice.name,
    nomenclador: practice.nomenclador,
    chapter: practice.chapter,
    practice_type: practice.practice_type,
    practice_requires_authorization: practice.requires_authorization,
    practice_waiting_period_days: practice.default_waiting_period_days,
    is_covered: body.is_covered !== false,
    waiting_period_days: waiting,
    effective_waiting_period_days: waiting ?? practice.default_waiting_period_days,
    copayment_amount: decimal(body.copayment_amount) ?? '0.00',
    requires_authorization: body.requires_authorization === true,
    notes: text(body.notes),
    created_at: now(),
  };
}

export function handleCoverageRequest(
  db: MockDB,
  url: string,
  method: string,
  body: Record<string, unknown>,
  params: Record<string, unknown>,
): CoverageResult | null {
  // --------------------------------------------------------------- payers
  if (url === '/api/v1/payers' && method === 'get') {
    const search = text(params.search)?.toLowerCase();
    if (!search) return ok(db.payers);
    return ok(
      db.payers.filter(
        (payer) =>
          payer.name.toLowerCase().includes(search) ||
          payer.code.toLowerCase().includes(search),
      ),
    );
  }
  if (url === '/api/v1/payers' && method === 'post') {
    if (db.payers.some((payer) => payer.code === body.code)) {
      return err(409, 'Código de financiador duplicado');
    }
    const payer: PayerRead = {
      id: uuid(),
      name: String(body.name ?? ''),
      code: String(body.code ?? ''),
      tax_id: text(body.tax_id),
      created_at: now(),
    };
    db.payers.push(payer);
    saveDB(db);
    return ok(payer, 201);
  }

  const payerMatch = url.match(/^\/api\/v1\/payers\/([^/]+)$/);
  if (payerMatch) {
    const payerId = payerMatch[1];
    const payer = db.payers.find((item) => item.id === payerId);
    if (!payer) return err(404, 'Financiador inexistente');

    if (method === 'get') return ok(payer);
    if (method === 'put') {
      if (db.payers.some((item) => item.id !== payerId && item.code === body.code)) {
        return err(409, 'Código de financiador duplicado');
      }
      payer.name = String(body.name ?? payer.name);
      payer.code = String(body.code ?? payer.code);
      payer.tax_id = text(body.tax_id);
      saveDB(db);
      return ok(payer);
    }
    if (method === 'delete') {
      const blocked = blockedBy('No se puede eliminar el financiador porque está en uso', {
        planes: db.healthPlans.filter((plan) => plan.payer_id === payerId).length,
        coberturas: db.coverages.filter((item) => item.payer_id === payerId).length,
        aranceles: db.practiceTariffs.filter((item) => item.payer_id === payerId).length,
      });
      if (blocked) return blocked;
      db.payers = db.payers.filter((item) => item.id !== payerId);
      saveDB(db);
      return ok(undefined, 204);
    }
  }

  // ---------------------------------------------------------- health plans
  const payerPlansMatch = url.match(/^\/api\/v1\/payers\/([^/]+)\/health-plans$/);
  if (payerPlansMatch) {
    const payerId = payerPlansMatch[1];
    if (!db.payers.some((payer) => payer.id === payerId)) {
      return err(404, 'Financiador inexistente');
    }
    if (method === 'get') {
      return ok(db.healthPlans.filter((plan) => plan.payer_id === payerId));
    }
    if (method === 'post') {
      const duplicated = db.healthPlans.some(
        (plan) => plan.payer_id === payerId && plan.code === body.code,
      );
      if (duplicated) return err(409, 'Código de plan duplicado para el financiador');
      const plan: HealthPlanRead = {
        id: uuid(),
        payer_id: payerId,
        name: String(body.name ?? ''),
        code: String(body.code ?? ''),
        created_at: now(),
      };
      db.healthPlans.push(plan);
      saveDB(db);
      return ok(plan, 201);
    }
  }

  if (url === '/api/v1/health-plans' && method === 'get') {
    const payerId = text(params.payer_id);
    if (payerId && !db.payers.some((payer) => payer.id === payerId)) {
      return err(404, 'Financiador inexistente');
    }
    return ok(payerId ? db.healthPlans.filter((plan) => plan.payer_id === payerId) : db.healthPlans);
  }

  const planMatch = url.match(/^\/api\/v1\/health-plans\/([^/]+)$/);
  if (planMatch) {
    const planId = planMatch[1];
    const plan = db.healthPlans.find((item) => item.id === planId);
    if (!plan) return err(404, 'Plan inexistente');

    if (method === 'get') return ok(plan);
    if (method === 'put') {
      const duplicated = db.healthPlans.some(
        (item) => item.id !== planId && item.payer_id === plan.payer_id && item.code === body.code,
      );
      if (duplicated) return err(409, 'Código de plan duplicado para el financiador');
      plan.name = String(body.name ?? plan.name);
      plan.code = String(body.code ?? plan.code);
      saveDB(db);
      return ok(plan);
    }
    if (method === 'delete') {
      const blocked = blockedBy('No se puede eliminar el plan porque está en uso', {
        coberturas: db.coverages.filter((item) => item.health_plan_id === planId).length,
        aranceles: db.practiceTariffs.filter((item) => item.health_plan_id === planId).length,
      });
      if (blocked) return blocked;
      db.healthPlans = db.healthPlans.filter((item) => item.id !== planId);
      saveDB(db);
      return ok(undefined, 204);
    }
  }

  // ------------------------------------------------- cartilla of a plan
  const cartillaMatch = url.match(/^\/api\/v1\/health-plans\/([^/]+)\/practices$/);
  if (cartillaMatch) {
    const planId = cartillaMatch[1];
    if (!db.healthPlans.some((plan) => plan.id === planId)) return err(404, 'Plan inexistente');

    if (method === 'get') {
      const search = text(params.search)?.toLowerCase();
      return ok(
        db.planPractices
          .filter(
            (entry) =>
              entry.health_plan_id === planId &&
              (!params.chapter || entry.chapter === params.chapter) &&
              (!params.only_covered || entry.is_covered) &&
              (!search ||
                entry.practice_code.toLowerCase().includes(search) ||
                entry.practice_name.toLowerCase().includes(search)),
          )
          .sort((a, b) => a.practice_code.localeCompare(b.practice_code)),
      );
    }
    if (method === 'post') {
      const practiceId = text(body.practice_id);
      const practice = db.practices.find((item) => item.id === practiceId);
      if (!practice) return err(404, 'Práctica inexistente');
      const duplicated = db.planPractices.some(
        (entry) => entry.health_plan_id === planId && entry.practice_id === practiceId,
      );
      if (duplicated) return err(409, 'La práctica ya está en la cartilla del plan');
      const entry = planPracticeFrom(planId, practice, body);
      db.planPractices.push(entry);
      saveDB(db);
      return ok(entry, 201);
    }
  }

  const bulkMatch = url.match(/^\/api\/v1\/health-plans\/([^/]+)\/practices\/bulk$/);
  if (bulkMatch && method === 'post') {
    const planId = bulkMatch[1];
    if (!db.healthPlans.some((plan) => plan.id === planId)) return err(404, 'Plan inexistente');
    const requested = Array.isArray(body.practice_ids) ? (body.practice_ids as string[]) : [];
    if (requested.some((id) => !db.practices.some((practice) => practice.id === id))) {
      return err(404, 'Práctica inexistente');
    }
    const created: HealthPlanPracticeRead[] = [];
    const skipped: string[] = [];
    for (const practiceId of [...new Set(requested)]) {
      const already = db.planPractices.some(
        (entry) => entry.health_plan_id === planId && entry.practice_id === practiceId,
      );
      if (already) {
        // Las condiciones ya negociadas no se pisan.
        skipped.push(practiceId);
        continue;
      }
      const practice = db.practices.find((item) => item.id === practiceId)!;
      const entry = planPracticeFrom(planId, practice, body);
      db.planPractices.push(entry);
      created.push(entry);
    }
    saveDB(db);
    return ok({ created, skipped_practice_ids: skipped }, 201);
  }

  const cartillaEntryMatch = url.match(
    /^\/api\/v1\/health-plans\/([^/]+)\/practices\/([^/]+)$/,
  );
  if (cartillaEntryMatch && method !== 'post') {
    const [, planId, entryId] = cartillaEntryMatch;
    const entry = db.planPractices.find(
      (item) => item.id === entryId && item.health_plan_id === planId,
    );
    if (!entry) return err(404, 'La práctica no está en la cartilla del plan');

    if (method === 'put') {
      const practice = db.practices.find((item) => item.id === entry.practice_id);
      const waiting = waitingPeriodOf(body);
      entry.is_covered = body.is_covered !== false;
      entry.waiting_period_days = waiting;
      entry.practice_waiting_period_days = practice?.default_waiting_period_days ?? 0;
      entry.effective_waiting_period_days =
        waiting ?? practice?.default_waiting_period_days ?? 0;
      entry.copayment_amount = decimal(body.copayment_amount) ?? '0.00';
      entry.requires_authorization = body.requires_authorization === true;
      entry.notes = text(body.notes);
      saveDB(db);
      return ok(entry);
    }
    if (method === 'delete') {
      db.planPractices = db.planPractices.filter((item) => item.id !== entryId);
      saveDB(db);
      return ok(undefined, 204);
    }
  }

  // ------------------------------------------------------------ coverages
  const patientCoveragesMatch = url.match(/^\/api\/v1\/patients\/([^/]+)\/coverages$/);
  if (patientCoveragesMatch) {
    const patientId = patientCoveragesMatch[1];
    if (!db.patients.some((patient) => patient.id === patientId)) {
      return err(404, 'Paciente inexistente');
    }
    if (method === 'get') {
      return ok(db.coverages.filter((item) => item.patient_id === patientId));
    }
    if (method === 'post') {
      const fields = coverageFields(db, body);
      if (isCoverageError(fields)) return fields;
      const coverage: PatientCoverageRead = {
        id: uuid(),
        patient_id: patientId,
        created_at: now(),
        ...fields,
      };
      db.coverages.push(coverage);
      saveDB(db);
      return ok(coverage, 201);
    }
  }

  const coverageMatch = url.match(/^\/api\/v1\/coverages\/([^/]+)$/);
  if (coverageMatch) {
    const coverageId = coverageMatch[1];
    const coverage = db.coverages.find((item) => item.id === coverageId);
    if (!coverage) return err(404, 'Cobertura inexistente');

    if (method === 'get') return ok(coverage);
    if (method === 'put') {
      const fields = coverageFields(db, body);
      if (isCoverageError(fields)) return fields;
      Object.assign(coverage, fields);
      saveDB(db);
      return ok(coverage);
    }
    if (method === 'delete') {
      const blocked = blockedBy('No se puede eliminar la cobertura porque está en uso', {
        admisiones: db.admissions.filter((item) => item.coverage_id === coverageId).length,
        autorizaciones: db.authorizations.filter(
          (item) => item.patient_coverage_id === coverageId,
        ).length,
      });
      if (blocked) return blocked;
      db.coverages = db.coverages.filter((item) => item.id !== coverageId);
      saveDB(db);
      return ok(undefined, 204);
    }
  }

  return null;
}
