/**
 * Mock handlers for the medical practice catalog: the nomenclador entries, the payer
 * catalog behind them and the tariffs agreed for each practice.
 *
 * They mirror the API rules: the code is unique inside its nomenclador, the amounts are
 * derived from the units when only the unit value is informed, a payer/plan cannot have
 * two tariffs starting the same day, and the plan tariff prevails over the payer one and
 * the payer one over the institutional tariff.
 */
import type {
  ChargeCategory,
  ChargeItemRead,
  HospitalizationPracticeRead,
  MedicalPracticeRead,
  MedicalPracticeTariffRead,
  Nomenclador,
  PatientCoverageRead,
  PlanCoverageCheckRead,
  PracticeChapter,
  PracticeSetting,
  PracticeType,
} from './model';
import { accountIdOf } from './mock-account';
import { type MockDB, now, saveDB, uuid } from './mock-db';
import { recordEvent } from './mock-workflow';

type Ok = { kind: 'ok'; data: unknown; status: number };
type Err = { kind: 'error'; status: number; detail: string };
export type PracticeResult = Ok | Err;

const ok = (data: unknown, status = 200): Ok => ({ kind: 'ok', data, status });
const err = (status: number, detail: string): Err => ({ kind: 'error', status, detail });

const decimal = (value: unknown, fallback: string | null = null): string | null => {
  if (value === null || value === undefined || value === '') return fallback;
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return fallback;
  return parsed.toFixed(2);
};

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() !== '' ? value : null;

const flag = (value: unknown, fallback = false): boolean =>
  typeof value === 'boolean' ? value : fallback;

const today = () => new Date().toISOString().slice(0, 10);

function practiceFromBody(
  body: Record<string, unknown>,
  base: Partial<MedicalPracticeRead> = {},
): MedicalPracticeRead {
  return {
    id: base.id ?? uuid(),
    nomenclador: (body.nomenclador as Nomenclador) ?? 'NACIONAL',
    code: String(body.code ?? '').trim(),
    name: String(body.name ?? '').trim(),
    description: text(body.description),
    chapter: body.chapter as PracticeChapter,
    practice_type: body.practice_type as PracticeType,
    setting: (body.setting as PracticeSetting) ?? 'AMBOS',
    galeno_units: decimal(body.galeno_units, '0.00')!,
    expense_units: decimal(body.expense_units, '0.00')!,
    anesthesia_units: decimal(body.anesthesia_units, '0.00')!,
    biochemical_units: decimal(body.biochemical_units, '0.00')!,
    radiology_units: decimal(body.radiology_units, '0.00')!,
    requires_authorization: flag(body.requires_authorization),
    requires_consent: flag(body.requires_consent),
    default_waiting_period_days: Number(body.default_waiting_period_days ?? 0) || 0,
    is_nursing_task: flag(body.is_nursing_task),
    is_active: flag(body.is_active, true),
    valid_from: text(body.valid_from),
    valid_until: text(body.valid_until),
    notes: text(body.notes),
    created_at: base.created_at ?? now(),
  };
}

/** Same derivation as ``MedicalPracticeService._tariff_values``. */
function tariffFromBody(
  db: MockDB,
  practice: MedicalPracticeRead,
  body: Record<string, unknown>,
  base: Partial<MedicalPracticeTariffRead> = {},
): PracticeResult | MedicalPracticeTariffRead {
  const validFrom = text(body.valid_from);
  if (!validFrom) return err(422, 'Informe la vigencia del valor');
  const validUntil = text(body.valid_until);
  if (validUntil && validUntil < validFrom) return err(422, 'La vigencia informada es inválida');

  let payerId = text(body.payer_id);
  const planId = text(body.health_plan_id);
  if (payerId && !db.payers.some((payer) => payer.id === payerId)) {
    return err(404, 'Financiador inexistente');
  }
  if (planId) {
    const plan = db.healthPlans.find((item) => item.id === planId);
    if (!plan) return err(404, 'Plan inexistente');
    if (payerId && plan.payer_id !== payerId) {
      return err(422, 'El plan no pertenece al financiador informado');
    }
    payerId = plan.payer_id;
  }

  const unitValue = decimal(body.unit_value);
  let fee = decimal(body.professional_fee);
  let expense = decimal(body.expense_amount);
  if (unitValue !== null) {
    if (fee === null) fee = (Number(practice.galeno_units) * Number(unitValue)).toFixed(2);
    if (expense === null) expense = (Number(practice.expense_units) * Number(unitValue)).toFixed(2);
  }
  fee = fee ?? '0.00';
  expense = expense ?? '0.00';
  const total = decimal(body.total_amount) ?? (Number(fee) + Number(expense)).toFixed(2);
  if (Number(total) <= 0) {
    return err(422, 'Informe el valor de la unidad, los importes o el total de la práctica');
  }

  const duplicated = db.practiceTariffs.some(
    (item) =>
      item.id !== base.id &&
      item.practice_id === practice.id &&
      item.payer_id === payerId &&
      item.health_plan_id === planId &&
      item.valid_from === validFrom,
  );
  if (duplicated) return err(409, 'Ya existe un valor para esa cobertura con la misma vigencia');

  return {
    id: base.id ?? uuid(),
    practice_id: practice.id,
    payer_id: payerId,
    health_plan_id: planId,
    unit_value: unitValue,
    professional_fee: fee,
    expense_amount: expense,
    total_amount: total,
    coinsurance: decimal(body.coinsurance, '0.00')!,
    currency: (text(body.currency) ?? 'ARS').toUpperCase(),
    valid_from: validFrom,
    valid_until: validUntil,
    notes: text(body.notes),
    created_at: base.created_at ?? now(),
  };
}

/** Plan tariff first, then payer, then the institutional one. */
function effectiveTariff(
  db: MockDB,
  practiceId: string,
  payerId: string | null,
  planId: string | null,
  on: string,
): MedicalPracticeTariffRead | null {
  const current = db.practiceTariffs.filter(
    (tariff) =>
      tariff.practice_id === practiceId &&
      tariff.valid_from <= on &&
      (tariff.valid_until === null || tariff.valid_until >= on),
  );
  const pick = (predicate: (tariff: MedicalPracticeTariffRead) => boolean) =>
    current.filter(predicate).sort((a, b) => b.valid_from.localeCompare(a.valid_from))[0] ?? null;
  const scopes: ((tariff: MedicalPracticeTariffRead) => boolean)[] = [];
  if (planId) scopes.push((tariff) => tariff.health_plan_id === planId);
  if (payerId) {
    scopes.push((tariff) => tariff.payer_id === payerId && tariff.health_plan_id === null);
  }
  scopes.push((tariff) => tariff.payer_id === null && tariff.health_plan_id === null);
  for (const scope of scopes) {
    const tariff = pick(scope);
    if (tariff) return tariff;
  }
  return null;
}

const CHARGE_CATEGORIES: Partial<Record<PracticeType, ChargeCategory>> = {
  CONSULTA: 'PROFESSIONAL_FEE',
  PRACTICA: 'PROCEDURE',
  CIRUGIA: 'PROCEDURE',
  ANESTESIA: 'PROCEDURE',
  LABORATORIO: 'LABORATORY',
  IMAGENES: 'IMAGING',
  INTERNACION: 'HOSPITALIZATION_DAY',
  MODULO: 'HOSPITALIZATION_DAY',
};

/** Coverage row of the hospitalization, taken from its admission request. */
function coverageRowOf(db: MockDB, hospitalizationId: string): PatientCoverageRead | null {
  const admission = db.admissions.find((item) => item.hospitalization_id === hospitalizationId);
  return admission?.coverage_id
    ? db.coverages.find((item) => item.id === admission.coverage_id) ?? null
    : null;
}

/** Coverage of the hospitalization, taken from its admission request. */
function coverageOf(db: MockDB, hospitalizationId: string) {
  const coverage = coverageRowOf(db, hospitalizationId);
  return {
    payerId: coverage?.payer_id ?? null,
    planId: coverage?.health_plan_id ?? null,
  };
}

/** Misma evaluación que ``evaluate_coverage`` en la API. */
function evaluateCoverage(
  db: MockDB,
  hospitalizationId: string,
  practice: MedicalPracticeRead,
  on: string,
): PlanCoverageCheckRead {
  const base = {
    copayment_amount: '0.00',
    requires_authorization: false,
    waiting_period_days: 0,
    available_from: null,
    health_plan_id: null,
    message: null,
  };
  const coverage = coverageRowOf(db, hospitalizationId);
  if (!coverage) return { ...base, status: 'NO_COVERAGE', blocked: false };
  if (!coverage.health_plan_id) {
    return {
      ...base,
      status: 'NO_PLAN',
      blocked: false,
      message:
        `La cobertura de ${coverage.payer_name} no está vinculada a un plan del catálogo: ` +
        'no se aplican cartilla, carencias ni copagos',
    };
  }
  const planId = coverage.health_plan_id;
  const entry = db.planPractices.find(
    (item) => item.health_plan_id === planId && item.practice_id === practice.id,
  );
  if (!entry) {
    const loaded = db.planPractices.some((item) => item.health_plan_id === planId);
    if (!loaded) {
      // Cartilla vacía: nadie la cargó, no es que el plan no cubra nada.
      return { ...base, status: 'NO_CARTILLA', blocked: false, health_plan_id: planId };
    }
    return {
      ...base,
      status: 'NOT_LISTED',
      blocked: true,
      health_plan_id: planId,
      message: `La práctica ${practice.code} no está en la cartilla del plan de ${coverage.payer_name}`,
    };
  }

  // La carencia del plan pisa a la de la práctica; sin carencia propia rige la del catálogo.
  const waitingPeriod = entry.waiting_period_days ?? practice.default_waiting_period_days;
  const common = {
    copayment_amount: entry.copayment_amount,
    requires_authorization: entry.requires_authorization,
    waiting_period_days: waitingPeriod,
    health_plan_id: planId,
    available_from: null as string | null,
    message: null as string | null,
  };
  if (!entry.is_covered) {
    return {
      ...common,
      status: 'NOT_COVERED',
      blocked: true,
      message: `El plan de ${coverage.payer_name} no cubre la práctica ${practice.code}`,
    };
  }
  if (coverage.valid_from && waitingPeriod > 0) {
    const from = new Date(`${coverage.valid_from}T00:00:00`);
    from.setDate(from.getDate() + waitingPeriod);
    const availableFrom = from.toISOString().slice(0, 10);
    common.available_from = availableFrom;
    if (on < availableFrom) {
      return {
        ...common,
        status: 'WAITING_PERIOD',
        blocked: true,
        message:
          `La práctica ${practice.code} está en carencia hasta el ${availableFrom} ` +
          `(${waitingPeriod} días desde el alta de la cobertura)`,
      };
    }
  }
  if (waitingPeriod > 0 && !coverage.valid_from) {
    common.message =
      `La cobertura de ${coverage.payer_name} no tiene fecha de alta: la carencia de ` +
      `${waitingPeriod} días no puede verificarse`;
  }
  return { ...common, status: 'COVERED', blocked: false };
}

/** Aplica la cartilla al indicar o realizar; devuelve el error que corresponda. */
function enforceCoverage(
  db: MockDB,
  hospitalizationId: string,
  practice: MedicalPracticeRead,
  on: string,
  body: Record<string, unknown>,
  previousOverride: string | null = null,
): PracticeResult | PlanCoverageCheckRead {
  const check = evaluateCoverage(db, hospitalizationId, practice, on);
  const overrideReason = text(body.override_reason) ?? previousOverride;
  const override = body.override_coverage_rules === true || previousOverride !== null;
  if (override) {
    if (!overrideReason) {
      return err(
        422,
        'Informe el motivo por el que se registra la práctica fuera de la cartilla',
      );
    }
    return check;
  }
  if (check.blocked) {
    return err(409, check.message ?? 'La cartilla del plan no cubre la práctica');
  }
  if (check.requires_authorization && !text(body.authorization_number)) {
    return err(
      409,
      `El plan exige autorización para la práctica ${practice.code}: informe el número que ` +
        'dio el financiador',
    );
  }
  return check;
}

function isCheck(
  value: PracticeResult | PlanCoverageCheckRead,
): value is PlanCoverageCheckRead {
  return !('kind' in value);
}

/** The performance is what charges the account of the hospitalization. */
const APPLICANT_BY_ROLE: Record<string, string> = {
  NURSE: 'Enfermeria',
  DOCTOR: 'Profesional medico',
  ADMIN: 'Administracion del sistema',
};

function chargePractice(
  db: MockDB,
  order: HospitalizationPracticeRead,
  practice: MedicalPracticeRead,
  performedAt: string,
  unitPrice: string | null,
  check: PlanCoverageCheckRead,
  applicant?: string,
): PracticeResult | ChargeItemRead {
  const { payerId, planId } = coverageOf(db, order.hospitalization_id);
  let price = unitPrice;
  if (price === null) {
    const tariff = effectiveTariff(
      db,
      practice.id,
      payerId,
      planId,
      performedAt.slice(0, 10),
    );
    if (!tariff) {
      return err(
        422,
        `La práctica ${practice.code} no tiene un valor vigente para la cobertura de la ` +
          'internación: informe el importe',
      );
    }
    price = tariff.total_amount;
  }
  const quantity = Number(order.quantity);
  const item: ChargeItemRead = {
    id: uuid(),
    account_id: accountIdOf(order.hospitalization_id),
    practice_id: practice.id,
    practice_code: practice.code,
    category: CHARGE_CATEGORIES[practice.practice_type] ?? 'OTHER',
    description: `${practice.code} - ${practice.name}`,
    quantity: quantity.toFixed(3),
    unit_price: Number(price).toFixed(2),
    amount: (quantity * Number(price)).toFixed(2),
    charged_at: performedAt,
    recorded_by: null,
    notes: order.indication,
    status: 'ACTIVE',
    voided_at: null,
    voided_by: null,
    void_reason: null,
  };
  db.chargeItems.push(item);

  // El copago del plan es plata del afiliado: línea aparte, como en la API.
  const copayment = Number(check.copayment_amount) * quantity;
  let copaymentItem: ChargeItemRead | null = null;
  if (copayment > 0) {
    copaymentItem = {
      id: uuid(),
      account_id: accountIdOf(order.hospitalization_id),
      practice_id: practice.id,
      practice_code: practice.code,
      category: 'OTHER',
      description: `Copago ${practice.code} - ${practice.name}`,
      quantity: '1.000',
      unit_price: copayment.toFixed(2),
      amount: copayment.toFixed(2),
      charged_at: performedAt,
      recorded_by: null,
      notes: null,
      status: 'ACTIVE',
      voided_at: null,
      voided_by: null,
      void_reason: null,
    };
    db.chargeItems.push(copaymentItem);
  }

  order.status = 'PERFORMED';
  order.performed_at = performedAt;
  order.performed_by_user_name = order.performed_by_user_name ?? applicant ?? null;
  order.charge_item_id = item.id;
  order.charge = item;
  order.copayment_amount = check.copayment_amount;
  order.copayment_charge_item_id = copaymentItem?.id ?? null;
  recordEvent(db, 'PRACTICE_PERFORMED', {
    hospitalization_id: order.hospitalization_id,
    occurred_at: performedAt,
    details: {
      practice_code: practice.code,
      amount: item.amount,
      copayment: copayment.toFixed(2),
      plan_coverage: check.status,
    },
  });
  return item;
}

/** Sin cargo, o con el cargo anulado: la práctica está pendiente de facturar. */
function chargeIsVoid(db: MockDB, order: HospitalizationPracticeRead): boolean {
  if (!order.charge_item_id) return true;
  const item = db.chargeItems.find((charge) => charge.id === order.charge_item_id);
  return item === undefined || item.status === 'VOID';
}

/** Con el alta medica dada la internacion no recibe cambios, salvo de un administrador. */
const POST_DISCHARGE_STATUSES = [
  'CLINICALLY_DISCHARGED',
  'ADMINISTRATIVELY_DISCHARGED',
  'CLOSED',
];

export function postDischargeBlock(
  status: string,
  role: string | undefined,
): { status: number; detail: string } | null {
  if (!POST_DISCHARGE_STATUSES.includes(status)) return null;
  if ((role ?? '').toLowerCase() === 'admin') return null;
  return {
    status: 403,
    detail: 'La internación tiene alta médica: solo un administrador puede modificarla',
  };
}

const OPEN_HOSPITALIZATION_STATUSES = [
  'PENDING_BED',
  'IN_PROGRESS',
  'DISCHARGE_PLANNED',
  'CLINICALLY_DISCHARGED',
];

function isResult(
  value: PracticeResult | MedicalPracticeTariffRead | ChargeItemRead,
): value is PracticeResult {
  return 'kind' in value;
}

/** Panel de enfermeria: las practicas marcadas como suyas, con paciente y cama. */
function nursingTasks(db: MockDB, params: Record<string, unknown>): unknown[] {
  const pendingOnly = params.pending_only !== false && params.pending_only !== 'false';
  const on = text(params.on);
  return db.hospitalizationPractices
    .filter((order) => {
      const practice = db.practices.find((item) => item.id === order.practice_id);
      if (!practice?.is_nursing_task) return false;
      if (pendingOnly) return order.status === 'REQUESTED';
      if (!on) return true;
      const moment = order.performed_at ?? order.cancelled_at ?? order.prescribed_at;
      return moment.slice(0, 10) === on;
    })
    .map((order) => {
      const hospitalization = db.hospitalizations.find(
        (item) => item.id === order.hospitalization_id,
      );
      const patient = db.patients.find((item) => item.id === hospitalization?.patient_id);
      const assignment = db.bedAssignments.find(
        (item) => item.hospitalization_id === order.hospitalization_id && !item.ended_at,
      );
      const bed = db.beds.find((item) => item.id === assignment?.bed_id);
      const prescriber = db.professionals.find((item) => item.id === order.prescribed_by_id);
      return {
        id: order.id,
        hospitalization_id: order.hospitalization_id,
        practice_id: order.practice_id,
        practice_code: order.practice_code,
        practice_name: order.practice_name,
        status: order.status,
        quantity: order.quantity,
        patient_id: patient?.id ?? '',
        patient_name: patient ? `${patient.last_name}, ${patient.first_name}` : 'Paciente',
        ward: bed?.ward ?? null,
        room_code: bed?.room ?? null,
        bed_code: bed?.code ?? null,
        prescribed_by: prescriber
          ? `${prescriber.last_name}, ${prescriber.first_name}`
          : null,
        prescribed_at: order.prescribed_at,
        performed_at: order.performed_at,
        performed_by: order.performed_by_user_name,
        cancelled_at: order.cancelled_at,
        indication: order.indication,
        notes: order.notes,
      };
    });
}

export function handlePracticeRequest(
  db: MockDB,
  url: string,
  method: string,
  body: Record<string, unknown>,
  params: Record<string, unknown>,
  role?: string,
): PracticeResult | null {
  // ------------------------------------------------------------ practices
  if (url === '/api/v1/practices' && method === 'get') {
    const search = text(params.search)?.toLowerCase();
    const matches = db.practices.filter(
      (practice) =>
        (!params.nomenclador || practice.nomenclador === params.nomenclador) &&
        (!params.chapter || practice.chapter === params.chapter) &&
        (!params.practice_type || practice.practice_type === params.practice_type) &&
        (!params.setting ||
          practice.setting === params.setting ||
          practice.setting === 'AMBOS') &&
        (!search ||
          practice.code.toLowerCase().includes(search) ||
          practice.name.toLowerCase().includes(search)) &&
        (!params.only_active || practice.is_active),
    );
    return ok(
      [...matches].sort(
        (a, b) =>
          a.nomenclador.localeCompare(b.nomenclador) || a.code.localeCompare(b.code),
      ),
    );
  }

  if (url === '/api/v1/practices' && method === 'post') {
    const practice = practiceFromBody(body);
    if (
      db.practices.some(
        (item) => item.nomenclador === practice.nomenclador && item.code === practice.code,
      )
    ) {
      return err(409, 'Código de práctica duplicado en el nomenclador');
    }
    if (
      practice.valid_from &&
      practice.valid_until &&
      practice.valid_until < practice.valid_from
    ) {
      return err(422, 'La vigencia informada es inválida');
    }
    db.practices.push(practice);
    saveDB(db);
    return ok(practice, 201);
  }

  const practiceMatch = url.match(/^\/api\/v1\/practices\/([^/]+)$/);
  if (practiceMatch) {
    const index = db.practices.findIndex((item) => item.id === practiceMatch[1]);
    if (index === -1) return err(404, 'Práctica inexistente');
    const current = db.practices[index];
    if (method === 'get') return ok(current);
    if (method === 'put') {
      const updated = practiceFromBody(body, current);
      if (
        db.practices.some(
          (item) =>
            item.id !== current.id &&
            item.nomenclador === updated.nomenclador &&
            item.code === updated.code,
        )
      ) {
        return err(409, 'Código de práctica duplicado en el nomenclador');
      }
      if (updated.valid_from && updated.valid_until && updated.valid_until < updated.valid_from) {
        return err(422, 'La vigencia informada es inválida');
      }
      db.practices[index] = updated;
      saveDB(db);
      return ok(updated);
    }
    if (method === 'delete') {
      db.practices = db.practices.filter((item) => item.id !== current.id);
      db.practiceTariffs = db.practiceTariffs.filter((item) => item.practice_id !== current.id);
      saveDB(db);
      return ok(undefined, 204);
    }
  }

  // -------------------------------------------------------------- tariffs
  const effectiveMatch = url.match(/^\/api\/v1\/practices\/([^/]+)\/tariffs\/effective$/);
  if (effectiveMatch && method === 'get') {
    const practice = db.practices.find((item) => item.id === effectiveMatch[1]);
    if (!practice) return err(404, 'Práctica inexistente');
    const tariff = effectiveTariff(
      db,
      practice.id,
      text(params.payer_id),
      text(params.health_plan_id),
      text(params.on) ?? today(),
    );
    return tariff
      ? ok(tariff)
      : err(404, 'La práctica no tiene un valor vigente para esa cobertura');
  }

  const tariffsMatch = url.match(/^\/api\/v1\/practices\/([^/]+)\/tariffs$/);
  if (tariffsMatch) {
    const practice = db.practices.find((item) => item.id === tariffsMatch[1]);
    if (!practice) return err(404, 'Práctica inexistente');
    if (method === 'get') {
      const payerId = text(params.payer_id);
      return ok(
        db.practiceTariffs
          .filter(
            (tariff) =>
              tariff.practice_id === practice.id &&
              (!payerId || tariff.payer_id === payerId),
          )
          .sort((a, b) => b.valid_from.localeCompare(a.valid_from)),
      );
    }
    if (method === 'post') {
      const created = tariffFromBody(db, practice, body);
      if (isResult(created)) return created;
      db.practiceTariffs.push(created);
      saveDB(db);
      return ok(created, 201);
    }
  }

  const tariffMatch = url.match(/^\/api\/v1\/practices\/([^/]+)\/tariffs\/([^/]+)$/);
  if (tariffMatch && (method === 'put' || method === 'delete')) {
    const practice = db.practices.find((item) => item.id === tariffMatch[1]);
    if (!practice) return err(404, 'Práctica inexistente');
    const index = db.practiceTariffs.findIndex(
      (item) => item.id === tariffMatch[2] && item.practice_id === practice.id,
    );
    if (index === -1) return err(404, 'Valor de práctica inexistente');
    if (method === 'delete') {
      db.practiceTariffs = db.practiceTariffs.filter((item) => item.id !== tariffMatch[2]);
      saveDB(db);
      return ok(undefined, 204);
    }
    const updated = tariffFromBody(db, practice, body, db.practiceTariffs[index]);
    if (isResult(updated)) return updated;
    db.practiceTariffs[index] = updated;
    saveDB(db);
    return ok(updated);
  }

  // ------------------------------------------- practices of a hospitalization
  // --------------------------------------------------- tareas de enfermeria
  if (url === '/api/v1/nursing-tasks' && method === 'get') {
    return ok(nursingTasks(db, params));
  }

  const nursingMatch = url.match(/^\/api\/v1\/nursing-tasks\/([^/]+)\/(perform|cancel)$/);
  if (nursingMatch && method === 'post') {
    const [, orderId, action] = nursingMatch;
    const order = db.hospitalizationPractices.find((item) => item.id === orderId);
    if (!order) return err(404, 'Tarea inexistente');
    const practice = db.practices.find((item) => item.id === order.practice_id);
    if (!practice?.is_nursing_task) {
      return err(
        409,
        'La práctica no es una tarea de enfermería: regístrela desde la internación',
      );
    }
    return handlePracticeRequest(
      db,
      `/api/v1/hospitalizations/${order.hospitalization_id}/practices/${orderId}/${action}`,
      method,
      body,
      params,
      role,
    );
  }

  const coverageCheckMatch = url.match(
    /^\/api\/v1\/hospitalizations\/([^/]+)\/practices\/coverage-check$/,
  );
  if (coverageCheckMatch && method === 'get') {
    const hospitalizationId = coverageCheckMatch[1];
    if (!db.hospitalizations.some((item) => item.id === hospitalizationId)) {
      return err(404, 'Internación inexistente');
    }
    const practice = db.practices.find((item) => item.id === text(params.practice_id));
    if (!practice) return err(404, 'Práctica inexistente');
    const on = text(params.on) ?? now().slice(0, 10);
    return ok(evaluateCoverage(db, hospitalizationId, practice, on));
  }

  const hospPracticesMatch = url.match(/^\/api\/v1\/hospitalizations\/([^/]+)\/practices$/);
  if (hospPracticesMatch) {
    const hospitalizationId = hospPracticesMatch[1];
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');

    if (method === 'get') {
      return ok(
        db.hospitalizationPractices
          .filter((item) => item.hospitalization_id === hospitalizationId)
          .sort((a, b) => b.prescribed_at.localeCompare(a.prescribed_at)),
      );
    }
    if (method === 'post') {
      const locked = postDischargeBlock(hospitalization.status, role);
      if (locked) return err(locked.status, locked.detail);
      if (!OPEN_HOSPITALIZATION_STATUSES.includes(hospitalization.status)) {
        return err(409, 'La internación ya no admite prácticas');
      }
      const practice = db.practices.find((item) => item.id === text(body.practice_id));
      if (!practice) return err(404, 'Práctica inexistente');
      if (!practice.is_active) return err(409, 'La práctica no está vigente en el nomenclador');
      const prescribedBy = text(body.prescribed_by_id);
      if (!prescribedBy || !db.professionals.some((item) => item.id === prescribedBy)) {
        return err(404, 'Profesional prescriptor inexistente');
      }
      const performedBy = text(body.performed_by_id);
      if (performedBy && !db.professionals.some((item) => item.id === performedBy)) {
        return err(404, 'Profesional ejecutor inexistente');
      }

      const prescribedAt = text(body.prescribed_at) ?? now();
      const check = enforceCoverage(
        db,
        hospitalizationId,
        practice,
        (text(body.performed_at) ?? prescribedAt).slice(0, 10),
        body,
      );
      if (!isCheck(check)) return check;

      const order: HospitalizationPracticeRead = {
        id: uuid(),
        hospitalization_id: hospitalizationId,
        practice_id: practice.id,
        practice_code: practice.code,
        practice_name: practice.name,
        prescribed_by_id: prescribedBy,
        performed_by_id: performedBy,
        service_id: text(body.service_id),
        performed_by_user_id: null,
        performed_by_user_name: null,
        charge_item_id: null,
        status: 'REQUESTED',
        quantity: (Number(body.quantity ?? 1) || 1).toFixed(3),
        prescribed_at: prescribedAt,
        performed_at: null,
        cancelled_at: null,
        indication: text(body.indication),
        notes: text(body.notes),
        authorization_number: text(body.authorization_number),
        copayment_amount: check.copayment_amount,
        copayment_charge_item_id: null,
        coverage_override_reason:
          body.override_coverage_rules === true ? text(body.override_reason) : null,
        created_at: now(),
        charge: null,
      };
      recordEvent(db, 'PRACTICE_ORDERED', {
        hospitalization_id: hospitalizationId,
        occurred_at: order.prescribed_at,
        details: {
          practice_code: practice.code,
          prescribed_by_id: prescribedBy,
          plan_coverage: check.status,
          ...(order.coverage_override_reason ? { coverage_override: 'true' } : {}),
        },
      });

      const performedAt = text(body.performed_at);
      if (performedAt) {
        const charged = chargePractice(
          db,
          order,
          practice,
          performedAt,
          decimal(body.unit_price),
          check,
          APPLICANT_BY_ROLE[role ?? ''],
        );
        if (isResult(charged)) return charged;
      }
      db.hospitalizationPractices.push(order);
      saveDB(db);
      return ok(order, 201);
    }
  }

  const orderMatch = url.match(
    /^\/api\/v1\/hospitalizations\/([^/]+)\/practices\/([^/]+)\/(perform|cancel)$/,
  );
  if (orderMatch && method === 'post') {
    const [, hospitalizationId, orderId, action] = orderMatch;
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'Internación inexistente');
    const locked = postDischargeBlock(hospitalization.status, role);
    if (locked) return err(locked.status, locked.detail);
    const order = db.hospitalizationPractices.find(
      (item) => item.id === orderId && item.hospitalization_id === hospitalizationId,
    );
    if (!order) return err(404, 'Práctica de la internación inexistente');

    if (action === 'cancel') {
      if (order.status === 'PERFORMED' && !chargeIsVoid(db, order)) {
        return err(
          409,
          'La práctica realizada tiene un cargo activo: anúlelo en la cuenta antes de anular ' +
            'la práctica',
        );
      }
      if (order.status !== 'CANCELLED') {
        const copayment = db.chargeItems.find(
          (item) => item.id === order.copayment_charge_item_id,
        );
        if (copayment && copayment.status === 'ACTIVE') {
          copayment.status = 'VOID';
          copayment.voided_at = now();
          copayment.void_reason = 'Práctica anulada';
        }
        order.status = 'CANCELLED';
        order.cancelled_at = now();
        if (text(body.reason)) order.notes = text(body.reason);
        recordEvent(db, 'PRACTICE_CANCELLED', {
          hospitalization_id: hospitalizationId,
          details: { practice_code: order.practice_code, reason: text(body.reason) },
        });
        saveDB(db);
      }
      return ok(order);
    }

    // Una práctica realizada solo se vuelve a facturar si su cargo fue anulado.
    if (order.status === 'PERFORMED' && !chargeIsVoid(db, order)) {
      return err(
        409,
        'La práctica ya fue registrada como realizada: anule el cargo en la cuenta para ' +
          'volver a facturarla',
      );
    }
    if (order.status === 'CANCELLED') return err(409, 'La práctica está anulada');
    if (!OPEN_HOSPITALIZATION_STATUSES.includes(hospitalization.status)) {
      return err(409, 'La internación ya no admite prácticas');
    }
    const practice = db.practices.find((item) => item.id === order.practice_id);
    if (!practice) return err(404, 'Práctica inexistente');
    const performedBy = text(body.performed_by_id);
    if (performedBy) {
      if (!db.professionals.some((item) => item.id === performedBy)) {
        return err(404, 'Profesional ejecutor inexistente');
      }
      order.performed_by_id = performedBy;
    }
    const performedAt = text(body.performed_at) ?? now();
    const check = enforceCoverage(
      db,
      hospitalizationId,
      practice,
      performedAt.slice(0, 10),
      { ...body, authorization_number: body.authorization_number ?? order.authorization_number },
      order.coverage_override_reason,
    );
    if (!isCheck(check)) return check;
    if (text(body.authorization_number)) {
      order.authorization_number = text(body.authorization_number);
    }
    const charged = chargePractice(
      db,
      order,
      practice,
      performedAt,
      decimal(body.unit_price),
      check,
      APPLICANT_BY_ROLE[role ?? ''],
    );
    if (isResult(charged)) return charged;
    saveDB(db);
    return ok(order);
  }
  return null;
}
