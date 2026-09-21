import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getHospitalizationWorkflow } from '@/api/endpoints/hospitalization-workflow/hospitalization-workflow';
import type { ChargeItemRead, HospitalizationRead, PaymentMethod, PaymentRead } from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import { useAuth } from '@/auth/AuthContext';
import { isPostDischarge } from './lock';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Badge,
  Card,
  Field,
  FormError,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import { money } from '@/components/practices/labels';
import {
  ACCOUNT_STATUS_COLORS,
  ACCOUNT_STATUS_LABELS,
  CHARGE_CATEGORY_LABELS,
  PAYMENT_METHOD_LABELS,
  RESPONSIBLE_PARTY_LABELS,
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, Receipt, Wallet } from 'lucide-react';

/** Con la cuenta cerrada o anulada ya no se toca ningun cargo. */
const EDITABLE_STATUSES = ['OPEN', 'READY_FOR_REVIEW'];

export function AccountCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getHospitalizationWorkflow();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [voiding, setVoiding] = useState<ChargeItemRead | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [payOpen, setPayOpen] = useState(false);
  const [payment, setPayment] = useState({
    amount: '',
    method: 'CASH' as PaymentMethod,
    reference: '',
  });
  const [voidingPayment, setVoidingPayment] = useState<PaymentRead | null>(null);
  const [paymentReason, setPaymentReason] = useState('');

  const accountQuery = useQuery({
    queryKey: ['account', hosp.id],
    queryFn: () => api.getAccountApiV1HospitalizationsHospitalizationIdAccountGet(hosp.id),
    retry: false,
  });

  const closeModal = () => {
    setVoiding(null);
    setReason('');
  };

  const voidMutation = useMutation({
    mutationFn: ({ chargeItemId, voidReason }: { chargeItemId: string; voidReason: string }) =>
      api.voidChargeItemApiV1HospitalizationsHospitalizationIdAccountChargeItemsChargeItemIdVoidPost(
        hosp.id,
        chargeItemId,
        { reason: voidReason || null },
      ),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setError(null);
      closeModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo anular el cargo.')),
  });

  const payMutation = useMutation({
    mutationFn: () =>
      api.registerPaymentApiV1HospitalizationsHospitalizationIdAccountPaymentsPost(hosp.id, {
        amount: payment.amount,
        method: payment.method,
        reference: payment.reference.trim() || null,
      }),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setError(null);
      setPayOpen(false);
      setPayment({ amount: '', method: 'CASH', reference: '' });
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo registrar el pago.')),
  });

  const voidPaymentMutation = useMutation({
    mutationFn: ({ paymentId, voidReason }: { paymentId: string; voidReason: string }) =>
      api.voidPaymentApiV1HospitalizationsHospitalizationIdAccountPaymentsPaymentIdVoidPost(
        hosp.id,
        paymentId,
        { reason: voidReason || null },
      ),
    onSuccess: () => {
      invalidateHospitalization(queryClient, hosp.id);
      setError(null);
      setVoidingPayment(null);
      setPaymentReason('');
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo anular el pago.')),
  });

  const account = accountQuery.data;

  if (accountQuery.isError || !account) {
    return (
      <Card className="p-6">
        <SectionTitle icon={<Receipt className="h-5 w-5 text-teal-600" />}>
          Cuenta de la internacion
        </SectionTitle>
        <p className="text-sm text-slate-400">La internacion todavia no tiene cuenta asociada.</p>
      </Card>
    );
  }

  const items = account.charge_items ?? [];
  const payments = account.payments ?? [];
  const balance = Number(account.patient_balance ?? 0);
  // Despues del alta medica la cuenta solo la corrige un admin.
  const canEdit =
    canManage &&
    EDITABLE_STATUSES.includes(account.status) &&
    (!isPostDischarge(hosp.status) || user?.role === 'ADMIN');

  return (
    <Card className="p-6">
      <SectionTitle icon={<Receipt className="h-5 w-5 text-teal-600" />}>
        Cuenta de la internacion
      </SectionTitle>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Badge
          status={ACCOUNT_STATUS_LABELS[account.status]}
          color={ACCOUNT_STATUS_COLORS[account.status]}
        />
        <div className="text-right">
          <p className="text-xs text-slate-400">Total a facturar</p>
          <p className="text-lg font-bold text-slate-800">{money(account.total_amount)}</p>
          {Number(account.voided_amount) > 0 && (
            <p className="text-xs text-slate-400">
              Anulado: {money(account.voided_amount)}
            </p>
          )}
        </div>
      </div>

      {/* Lo del financiador se factura por convenio; lo del paciente se cobra antes del alta. */}
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        {[
          ['A la cobertura', money(account.payer_amount)],
          ['A cargo del paciente', money(account.patient_amount)],
          ['Cobrado', money(account.paid_amount)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg bg-slate-50 px-3 py-2">
            <p className="text-xs text-slate-400">{label}</p>
            <p className="text-sm font-semibold text-slate-700">{value}</p>
          </div>
        ))}
        <div
          className={`rounded-lg px-3 py-2 ${
            balance > 0 ? 'bg-amber-50' : 'bg-emerald-50'
          }`}
        >
          <p className={`text-xs ${balance > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
            Saldo del paciente
          </p>
          <p
            className={`text-sm font-bold ${
              balance > 0 ? 'text-amber-700' : 'text-emerald-700'
            }`}
          >
            {money(account.patient_balance)}
          </p>
        </div>
      </div>

      {balance > 0 && (
        <p className="mb-4 rounded-lg bg-amber-50 px-4 py-2 text-xs font-medium text-amber-700">
          El alta administrativa no sale hasta que el paciente cancele su saldo.
        </p>
      )}

      {items.length === 0 ? (
        <p className="text-sm text-slate-400">La cuenta todavia no tiene cargos.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Cargo</th>
                <th className="px-3 py-2 text-left font-semibold">Paga</th>
                <th className="px-3 py-2 text-right font-semibold">Cantidad</th>
                <th className="px-3 py-2 text-right font-semibold">Unitario</th>
                <th className="px-3 py-2 text-right font-semibold">Importe</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((item) => {
                const isVoid = item.status === 'VOID';
                return (
                  <tr key={item.id} className={isVoid ? 'bg-slate-50 text-slate-400' : ''}>
                    <td className="px-3 py-2">
                      <p className={`font-medium ${isVoid ? 'line-through' : 'text-slate-700'}`}>
                        {item.description}
                      </p>
                      <p className="text-xs text-slate-400">
                        {CHARGE_CATEGORY_LABELS[item.category]}
                        {item.practice_code ? ` · Practica ${item.practice_code}` : ''} ·{' '}
                        {formatDateTime(item.charged_at)}
                      </p>
                      {isVoid && (
                        <p className="text-xs font-semibold text-red-500">
                          Anulado {formatDateTime(item.voided_at ?? null)}
                          {item.void_reason ? `: ${item.void_reason}` : ''}
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {RESPONSIBLE_PARTY_LABELS[item.responsible_party]}
                    </td>
                    <td className="px-3 py-2 text-right">{Number(item.quantity)}</td>
                    <td className="px-3 py-2 text-right">{money(item.unit_price)}</td>
                    <td
                      className={`px-3 py-2 text-right font-semibold ${
                        isVoid ? 'line-through' : 'text-slate-800'
                      }`}
                    >
                      {money(item.amount)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {canEdit && !isVoid && (
                        <ActionButton
                          tone="danger"
                          onClick={() => {
                            setVoiding(item);
                            setError(null);
                          }}
                        >
                          <Ban className="h-4 w-4" />
                          Anular
                        </ActionButton>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-semibold text-slate-700">Pagos del paciente</p>
          {canEdit && balance > 0 && (
            <ActionButton
              tone="teal"
              onClick={() => {
                setPayment({ amount: account.patient_balance ?? '', method: 'CASH', reference: '' });
                setError(null);
                setPayOpen(true);
              }}
            >
              <Wallet className="h-4 w-4" />
              Registrar pago
            </ActionButton>
          )}
        </div>
        {payments.length === 0 ? (
          <p className="text-sm text-slate-400">Todavia no se registraron pagos.</p>
        ) : (
          <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
            {payments.map((item) => {
              const isVoid = item.status === 'VOID';
              return (
                <div
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-2"
                >
                  <div>
                    <p
                      className={`text-sm font-semibold ${
                        isVoid ? 'text-slate-400 line-through' : 'text-slate-700'
                      }`}
                    >
                      {money(item.amount)} · {PAYMENT_METHOD_LABELS[item.method]}
                    </p>
                    <p className="text-xs text-slate-400">
                      {formatDateTime(item.paid_at)}
                      {item.reference ? ` · Comprobante ${item.reference}` : ''}
                      {item.received_by ? ` · ${item.received_by}` : ''}
                    </p>
                    {isVoid && (
                      <p className="text-xs font-semibold text-red-500">
                        Anulado {formatDateTime(item.voided_at ?? null)}
                        {item.void_reason ? `: ${item.void_reason}` : ''}
                      </p>
                    )}
                  </div>
                  {canEdit && !isVoid && (
                    <ActionButton
                      tone="danger"
                      onClick={() => {
                        setVoidingPayment(item);
                        setPaymentReason('');
                        setError(null);
                      }}
                    >
                      <Ban className="h-4 w-4" />
                      Anular
                    </ActionButton>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <FormError message={error} />

      <Modal open={payOpen} onClose={() => setPayOpen(false)} title="Registrar pago">
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
            Saldo a cobrar: {money(account.patient_balance)}. No se puede cobrar mas de lo que
            el paciente adeuda.
          </p>
          <Field label="Importe">
            <input
              type="number"
              min="0"
              step="0.01"
              value={payment.amount}
              onChange={(event) => setPayment({ ...payment, amount: event.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Medio de pago">
            <select
              value={payment.method}
              onChange={(event) =>
                setPayment({ ...payment, method: event.target.value as PaymentMethod })
              }
              className={inputClass}
            >
              {Object.entries(PAYMENT_METHOD_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Comprobante">
            <input
              type="text"
              value={payment.reference}
              onChange={(event) => setPayment({ ...payment, reference: event.target.value })}
              placeholder="Numero de recibo, cupon o transferencia"
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={() => setPayOpen(false)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="primary"
              disabled={payMutation.isPending || Number(payment.amount) <= 0}
              onClick={() => payMutation.mutate()}
            >
              {payMutation.isPending ? 'Registrando...' : 'Registrar pago'}
            </ActionButton>
          </div>
        </div>
      </Modal>

      <Modal
        open={voidingPayment !== null}
        onClose={() => setVoidingPayment(null)}
        title="Anular pago"
      >
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
            {money(voidingPayment?.amount ?? '0')}. El pago queda registrado como anulado y el
            importe vuelve a quedar adeudado.
          </p>
          <Field label="Motivo de la anulacion">
            <input
              type="text"
              value={paymentReason}
              onChange={(event) => setPaymentReason(event.target.value)}
              placeholder="Cupon rechazado, importe equivocado..."
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={() => setVoidingPayment(null)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="danger"
              disabled={voidPaymentMutation.isPending}
              onClick={() =>
                voidingPayment &&
                voidPaymentMutation.mutate({
                  paymentId: voidingPayment.id,
                  voidReason: paymentReason.trim(),
                })
              }
            >
              {voidPaymentMutation.isPending ? 'Anulando...' : 'Anular pago'}
            </ActionButton>
          </div>
        </div>
      </Modal>

      <Modal open={voiding !== null} onClose={closeModal} title="Anular cargo">
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
            {voiding?.description} — {money(voiding?.amount ?? '0')}. El cargo queda registrado en
            la cuenta y deja de sumar al total.
          </p>
          <Field label="Motivo de la anulacion">
            <input
              type="text"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Cargado por error, importe equivocado..."
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={closeModal}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="danger"
              disabled={voidMutation.isPending}
              onClick={() =>
                voiding &&
                voidMutation.mutate({ chargeItemId: voiding.id, voidReason: reason.trim() })
              }
            >
              {voidMutation.isPending ? 'Anulando...' : 'Anular cargo'}
            </ActionButton>
          </div>
        </div>
      </Modal>
    </Card>
  );
}

export default AccountCard;
