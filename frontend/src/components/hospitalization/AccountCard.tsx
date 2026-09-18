import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getHospitalizationWorkflow } from '@/api/endpoints/hospitalization-workflow/hospitalization-workflow';
import type { ChargeItemRead, HospitalizationRead } from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
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
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, Receipt } from 'lucide-react';

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
  const [voiding, setVoiding] = useState<ChargeItemRead | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

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
  const canEdit = canManage && EDITABLE_STATUSES.includes(account.status);

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

      {items.length === 0 ? (
        <p className="text-sm text-slate-400">La cuenta todavia no tiene cargos.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Cargo</th>
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

      <FormError message={error} />

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
