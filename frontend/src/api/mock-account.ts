/**
 * Mock handlers for the account of a hospitalization.
 *
 * The account is derived from the hospitalization (one per hospitalization, as the API
 * guarantees) and its charges live in ``db.chargeItems``. A wrong charge is voided, never
 * deleted: the line stays and stops adding to the total.
 */
import type { AccountRead, ChargeItemRead, HospitalizationRead } from './model';
import { type MockDB, now, saveDB } from './mock-db';
import { postDischargeBlock } from './mock-practices';
import { recordEvent } from './mock-workflow';

type Ok = { kind: 'ok'; data: unknown; status: number };
type Err = { kind: 'error'; status: number; detail: string };
export type AccountResult = Ok | Err;

const ok = (data: unknown, status = 200): Ok => ({ kind: 'ok', data, status });
const err = (status: number, detail: string): Err => ({ kind: 'error', status, detail });

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() !== '' ? value : null;

const sum = (items: ChargeItemRead[]) =>
  items.reduce((total, item) => total + Number(item.amount), 0).toFixed(2);

export function accountIdOf(hospitalizationId: string): string {
  return `acc-${hospitalizationId}`;
}

/** The account status follows the hospitalization, as the backfill migration did. */
function accountOf(db: MockDB, hospitalization: HospitalizationRead): AccountRead {
  const items = db.chargeItems.filter(
    (item) => item.account_id === accountIdOf(hospitalization.id),
  );
  const closed = hospitalization.status === 'CLOSED';
  return {
    id: accountIdOf(hospitalization.id),
    hospitalization_id: hospitalization.id,
    patient_id: hospitalization.patient_id,
    coverage_id:
      db.admissions.find((item) => item.hospitalization_id === hospitalization.id)?.coverage_id ??
      null,
    status: closed
      ? 'CLOSED'
      : hospitalization.clinically_discharged_at
        ? 'READY_FOR_REVIEW'
        : 'OPEN',
    currency: 'ARS',
    opened_at: hospitalization.admitted_at ?? now(),
    ready_for_review_at: hospitalization.clinically_discharged_at,
    closed_at: hospitalization.closed_at,
    total_amount: sum(items.filter((item) => item.status !== 'VOID')),
    voided_amount: sum(items.filter((item) => item.status === 'VOID')),
    charge_items: [...items].sort((a, b) => a.charged_at.localeCompare(b.charged_at)),
  };
}

export function handleAccountRequest(
  db: MockDB,
  url: string,
  method: string,
  body: Record<string, unknown>,
  role?: string,
): AccountResult | null {
  const accountMatch = url.match(/^\/api\/v1\/hospitalizations\/([^/]+)\/account$/);
  if (accountMatch && method === 'get') {
    const hospitalization = db.hospitalizations.find((item) => item.id === accountMatch[1]);
    if (!hospitalization) return err(404, 'La internación no tiene cuenta asociada');
    return ok(accountOf(db, hospitalization));
  }

  const voidMatch = url.match(
    /^\/api\/v1\/hospitalizations\/([^/]+)\/account\/charge-items\/([^/]+)\/void$/,
  );
  if (voidMatch && method === 'post') {
    const [, hospitalizationId, chargeItemId] = voidMatch;
    const hospitalization = db.hospitalizations.find((item) => item.id === hospitalizationId);
    if (!hospitalization) return err(404, 'La internación no tiene cuenta asociada');
    const locked = postDischargeBlock(hospitalization.status, role);
    if (locked) return err(locked.status, locked.detail);
    const account = accountOf(db, hospitalization);
    if (account.status === 'CLOSED' || account.status === 'CANCELLED') {
      return err(409, 'La cuenta está cerrada');
    }
    const item = db.chargeItems.find(
      (charge) => charge.id === chargeItemId && charge.account_id === account.id,
    );
    if (!item) return err(404, 'Cargo inexistente');
    if (item.status === 'VOID') return ok(item);

    item.status = 'VOID';
    item.voided_at = now();
    item.voided_by = text(body.actor);
    item.void_reason = text(body.reason);
    // The practice that generated the charge shows it as voided too.
    db.hospitalizationPractices
      .filter((practice) => practice.charge_item_id === item.id)
      .forEach((practice) => {
        practice.charge = item;
      });
    recordEvent(db, 'CHARGE_ITEM_VOIDED', {
      hospitalization_id: hospitalizationId,
      details: {
        charge_item_id: item.id,
        amount: item.amount,
        practice_code: item.practice_code ?? null,
        reason: item.void_reason,
      },
    });
    saveDB(db);
    return ok(item);
  }

  return null;
}
