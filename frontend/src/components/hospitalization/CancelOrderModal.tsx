import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { invalidateHospitalization } from '@/api/queryKeys';
import Modal from '@/components/Modal';
import { ActionButton, Field, FormError, inputClass } from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { XCircle } from 'lucide-react';

/** Baja de una orden medica programada cuyo paciente nunca llego: libera la cama reservada
 * y cancela la internacion, su cuenta y el episodio. */
export default function CancelOrderModal({
  admissionId,
  hospitalizationId,
  patientName,
  onClose,
}: {
  admissionId: string;
  hospitalizationId: string | null | undefined;
  patientName: string;
  onClose: () => void;
}) {
  const api = getDefault();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState('');

  const cancelMutation = useMutation({
    mutationFn: () =>
      api.cancelAdmissionApiV1AdmissionsAdmissionIdCancelPost(admissionId, {
        reason: reason.trim(),
      }),
    onSuccess: () => {
      if (hospitalizationId) invalidateHospitalization(queryClient, hospitalizationId);
      else queryClient.invalidateQueries({ queryKey: ['admissions'] });
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title="Cancelar orden programada">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          cancelMutation.mutate();
        }}
      >
        <p className="text-sm text-slate-500">
          {patientName} no se va a internar por esta orden. Se libera la cama reservada y se
          cancelan la internacion y su cuenta. No es un alta: el paciente nunca ingreso.
        </p>
        <Field label="Motivo">
          <textarea
            required
            minLength={3}
            maxLength={500}
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="El paciente no se presento, se reprogramo la internacion..."
            className={inputClass}
          />
        </Field>
        <FormError
          message={
            cancelMutation.isError
              ? apiErrorMessage(cancelMutation.error, 'No se pudo cancelar la orden.')
              : null
          }
        />
        <div className="flex justify-end gap-3 pt-2">
          <ActionButton tone="neutral" onClick={onClose}>
            Volver
          </ActionButton>
          <ActionButton
            tone="danger"
            type="submit"
            disabled={cancelMutation.isPending || reason.trim().length < 3}
          >
            <XCircle className="h-4 w-4" />
            {cancelMutation.isPending ? 'Cancelando...' : 'Cancelar orden'}
          </ActionButton>
        </div>
      </form>
    </Modal>
  );
}
