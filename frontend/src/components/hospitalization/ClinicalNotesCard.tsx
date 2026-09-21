import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getTreatments } from '@/api/endpoints/treatments/treatments';
import type { ClinicalNoteKind, ClinicalNoteRead, HospitalizationRead } from '@/api/model';
import { invalidateHospitalization } from '@/api/queryKeys';
import { useAuth } from '@/auth/AuthContext';
import { isPostDischarge } from './lock';
import Modal from '@/components/Modal';
import ProfessionalPicker from '@/components/professionals/ProfessionalPicker';
import {
  ActionButton,
  Badge,
  Card,
  Field,
  FormError,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import {
  CLINICAL_NOTE_KIND_COLORS,
  CLINICAL_NOTE_KIND_LABELS,
} from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDateTime } from '@/utils/format';
import { Ban, NotebookPen, Plus } from 'lucide-react';

export function ClinicalNotesCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getTreatments();
  const defaultApi = getDefault();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ClinicalNoteKind>('EVOLUTION');
  const [note, setNote] = useState('');
  const [authorId, setAuthorId] = useState('');
  const [serviceId, setServiceId] = useState('');
  const [voiding, setVoiding] = useState<ClinicalNoteRead | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const notesQuery = useQuery({
    queryKey: ['clinical-notes', hosp.id],
    queryFn: () => api.listNotesApiV1HospitalizationsHospitalizationIdNotesGet(hosp.id),
  });
  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => defaultApi.listServicesApiV1ServicesGet(),
  });

  const done = () => {
    invalidateHospitalization(queryClient, hosp.id);
    queryClient.invalidateQueries({ queryKey: ['clinical-notes', hosp.id] });
    setError(null);
  };

  const closeModal = () => {
    setOpen(false);
    setNote('');
    setAuthorId('');
    setServiceId('');
  };

  const addMutation = useMutation({
    mutationFn: () =>
      api.addNoteApiV1HospitalizationsHospitalizationIdNotesPost(hosp.id, {
        kind,
        note: note.trim(),
        author_id: authorId || null,
        service_id: serviceId || null,
      }),
    onSuccess: () => {
      done();
      closeModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar la nota.')),
  });

  const voidMutation = useMutation({
    mutationFn: () =>
      api.voidNoteApiV1HospitalizationsHospitalizationIdNotesNoteIdVoidPost(
        hosp.id,
        voiding!.id,
        { reason: reason.trim() || null },
      ),
    onSuccess: () => {
      done();
      setVoiding(null);
      setReason('');
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo anular la nota.')),
  });

  const notes = notesQuery.data ?? [];
  const services = servicesQuery.data ?? [];
  // Con el alta medica dada la historia queda cerrada, salvo para un admin.
  const canWrite = canManage && (!isPostDischarge(hosp.status) || user?.role === 'ADMIN');

  return (
    <Card className="p-6">
      <SectionTitle icon={<NotebookPen className="h-5 w-5 text-teal-600" />}>
        Evolucion, observaciones e interconsultas
      </SectionTitle>

      {notes.length === 0 ? (
        <p className="text-sm text-slate-400">Todavia no hay notas en esta internacion.</p>
      ) : (
        <div className="space-y-3">
          {notes.map((item) => {
            const isVoid = item.status === 'VOID';
            return (
              <div
                key={item.id}
                className={`rounded-lg border px-4 py-3 ${
                  isVoid ? 'border-slate-100 bg-slate-50/60' : 'border-slate-100'
                }`}
              >
                <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                  <Badge
                    status={CLINICAL_NOTE_KIND_LABELS[item.kind]}
                    color={CLINICAL_NOTE_KIND_COLORS[item.kind]}
                  />
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">
                      {formatDateTime(item.noted_at)}
                      {item.recorded_by_user_name ? ` · ${item.recorded_by_user_name}` : ''}
                    </span>
                    {canWrite && !isVoid && (
                      <button
                        type="button"
                        onClick={() => {
                          setVoiding(item);
                          setReason('');
                          setError(null);
                        }}
                        className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600"
                        title="Anular nota"
                      >
                        <Ban className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
                <p
                  className={`whitespace-pre-wrap text-sm ${
                    isVoid ? 'text-slate-400 line-through' : 'text-slate-700'
                  }`}
                >
                  {item.note}
                </p>
                {isVoid && (
                  <p className="mt-1 text-xs font-semibold text-red-500">
                    Anulada {formatDateTime(item.voided_at ?? null)}
                    {item.void_reason ? `: ${item.void_reason}` : ''}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      <FormError message={error} />

      {canWrite && (
        <div className="mt-4 flex justify-end">
          <ActionButton
            tone="primary"
            onClick={() => {
              setKind('EVOLUTION');
              setError(null);
              setOpen(true);
            }}
          >
            <Plus className="h-4 w-4" />
            Escribir nota
          </ActionButton>
        </div>
      )}

      <Modal open={open} onClose={closeModal} title="Nota en la historia">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            addMutation.mutate();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tipo">
              <select
                value={kind}
                onChange={(event) => setKind(event.target.value as ClinicalNoteKind)}
                className={inputClass}
              >
                {Object.entries(CLINICAL_NOTE_KIND_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Servicio">
              <select
                value={serviceId}
                onChange={(event) => setServiceId(event.target.value)}
                className={inputClass}
              >
                <option value="">Sin informar</option>
                {services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Profesional que atendio">
            <ProfessionalPicker value={authorId} onSelect={setAuthorId} />
          </Field>
          <Field label="Nota">
            <textarea
              required
              rows={5}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Evolucion del dia, observacion o lo que dejo indicado el interconsultor"
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={closeModal}>
              Cancelar
            </ActionButton>
            <ActionButton
              type="submit"
              tone="primary"
              disabled={addMutation.isPending || note.trim() === ''}
            >
              {addMutation.isPending ? 'Guardando...' : 'Guardar nota'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal open={voiding !== null} onClose={() => setVoiding(null)} title="Anular nota">
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
            La nota queda en la historia marcada como anulada: el texto no se borra.
          </p>
          <Field label="Motivo de la anulacion">
            <input
              type="text"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Cargada en el paciente equivocado..."
              className={inputClass}
            />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={() => setVoiding(null)}>
              Cancelar
            </ActionButton>
            <ActionButton
              tone="danger"
              disabled={voidMutation.isPending}
              onClick={() => voidMutation.mutate()}
            >
              {voidMutation.isPending ? 'Anulando...' : 'Anular nota'}
            </ActionButton>
          </div>
        </div>
      </Modal>
    </Card>
  );
}

export default ClinicalNotesCard;
