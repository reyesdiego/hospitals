import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getPractices } from '@/api/endpoints/practices/practices';
import { getPrescriptions } from '@/api/endpoints/prescriptions/prescriptions';
import { axiosInstance } from '@/api/custom-instance';
import type {
  DischargePrescriptionCreate,
  DischargePrescriptionRead,
  HospitalizationRead,
  PrescriptionKind,
} from '@/api/model';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Card,
  Field,
  FormError,
  SectionTitle,
  inputClass,
} from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { FileText, Pencil, Pill, Plus, Printer, Stethoscope, Trash2 } from 'lucide-react';

/** Se escriben al dar el alta y se cierran con el egreso administrativo. */
const EDITABLE_STATUSES = [
  'PENDING_BED',
  'IN_PROGRESS',
  'DISCHARGE_PLANNED',
  'CLINICALLY_DISCHARGED',
];

type PrescriptionForm = {
  kind: PrescriptionKind;
  practice_id: string;
  description: string;
  presentation: string;
  dosage: string;
  quantity: string;
  duration_days: string;
  instructions: string;
  prescribed_by_id: string;
};

const emptyForm: PrescriptionForm = {
  kind: 'MEDICATION',
  practice_id: '',
  description: '',
  presentation: '',
  dosage: '',
  quantity: '1',
  duration_days: '',
  instructions: '',
  prescribed_by_id: '',
};

function toPayload(form: PrescriptionForm): DischargePrescriptionCreate {
  const practice = form.kind === 'PRACTICE' ? form.practice_id : '';
  return {
    kind: form.kind,
    practice_id: practice || null,
    description: form.description.trim(),
    presentation: form.presentation.trim() || null,
    dosage: form.dosage.trim() || null,
    quantity: (Number(form.quantity) || 1).toFixed(2),
    duration_days: form.duration_days ? Number(form.duration_days) : null,
    instructions: form.instructions.trim() || null,
    prescribed_by_id: form.prescribed_by_id || null,
  };
}

function toForm(item: DischargePrescriptionRead): PrescriptionForm {
  return {
    kind: item.kind,
    practice_id: item.practice_id ?? '',
    description: item.description,
    presentation: item.presentation ?? '',
    dosage: item.dosage ?? '',
    quantity: String(Number(item.quantity)),
    duration_days: item.duration_days ? String(item.duration_days) : '',
    instructions: item.instructions ?? '',
    prescribed_by_id: item.prescribed_by_id ?? '',
  };
}

/**
 * Lo que el paciente se lleva al irse: la receta y las practicas que tiene que hacerse.
 * Se escriben al dar el alta medica y se imprimen en un PDF de dos hojas, una para la
 * farmacia y otra para el centro de diagnostico.
 */
export function DischargePrescriptionsCard({
  hosp,
  canManage,
}: {
  hosp: HospitalizationRead;
  canManage: boolean;
}) {
  const api = getPrescriptions();
  const catalog = getPractices();
  const defaultApi = getDefault();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<DischargePrescriptionRead | null>(null);
  const [form, setForm] = useState<PrescriptionForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  const prescriptionsQuery = useQuery({
    queryKey: ['discharge-prescriptions', hosp.id],
    queryFn: () =>
      api.listDischargePrescriptionsApiV1HospitalizationsHospitalizationIdDischargePrescriptionsGet(
        hosp.id,
      ),
    retry: false,
  });
  const catalogQuery = useQuery({
    queryKey: ['practices', { only_active: true }],
    queryFn: () => catalog.listPracticesApiV1PracticesGet({ only_active: true }),
    enabled: open,
  });
  const professionalsQuery = useQuery({
    queryKey: ['professionals'],
    queryFn: () => defaultApi.listProfessionalsApiV1ProfessionalsGet(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['discharge-prescriptions', hosp.id] });

  const closeModal = () => {
    setOpen(false);
    setEditing(null);
    setForm(emptyForm);
    setError(null);
  };

  const addMutation = useMutation({
    mutationFn: (data: DischargePrescriptionCreate) =>
      api.addDischargePrescriptionApiV1HospitalizationsHospitalizationIdDischargePrescriptionsPost(
        hosp.id,
        data,
      ),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar la indicacion.')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: DischargePrescriptionCreate }) =>
      api.updateDischargePrescriptionApiV1HospitalizationsHospitalizationIdDischargePrescriptionsPrescriptionIdPut(
        hosp.id,
        id,
        data,
      ),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar la indicacion.')),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) =>
      api.removeDischargePrescriptionApiV1HospitalizationsHospitalizationIdDischargePrescriptionsPrescriptionIdDelete(
        hosp.id,
        id,
      ),
    onSuccess: invalidate,
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo quitar la indicacion.')),
  });

  /** El PDF viaja con la sesion, asi que se descarga y se abre desde memoria. */
  const print = async () => {
    setError(null);
    setPrinting(true);
    try {
      const response = await axiosInstance.get(
        `/api/v1/hospitalizations/${hosp.id}/discharge-prescriptions/pdf`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
      window.open(url, '_blank', 'noopener');
      // Se libera despues de que el navegador lo tomo.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (printError) {
      setError(apiErrorMessage(printError, 'No se pudo generar el PDF.'));
    } finally {
      setPrinting(false);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const data = toPayload(form);
    if (editing) {
      updateMutation.mutate({ id: editing.id, data });
      return;
    }
    addMutation.mutate(data);
  };

  const openCreate = (kind: PrescriptionKind) => {
    setEditing(null);
    setForm({ ...emptyForm, kind });
    setError(null);
    setOpen(true);
  };

  const openEdit = (item: DischargePrescriptionRead) => {
    setEditing(item);
    setForm(toForm(item));
    setError(null);
    setOpen(true);
  };

  const items = prescriptionsQuery.data ?? [];
  const medications = items.filter((item) => item.kind === 'MEDICATION');
  const practices = items.filter((item) => item.kind === 'PRACTICE');
  const professionals = professionalsQuery.data ?? [];
  const editable = canManage && EDITABLE_STATUSES.includes(hosp.status);
  const isSaving = addMutation.isPending || updateMutation.isPending;

  const row = (item: DischargePrescriptionRead) => (
    <li key={item.id} className="flex items-start justify-between gap-3 px-4 py-3">
      <div>
        <p className="text-sm font-semibold text-slate-700">
          {item.description}
          {item.presentation ? ` · ${item.presentation}` : ''}
          {Number(item.quantity) !== 1 && (
            <span className="ml-2 text-xs text-slate-500">x{Number(item.quantity)}</span>
          )}
        </p>
        <p className="text-xs text-slate-500">
          {item.dosage ?? ''}
          {item.duration_days ? ` · ${item.duration_days} dias` : ''}
        </p>
        {item.instructions && (
          <p className="mt-0.5 text-xs italic text-slate-500">{item.instructions}</p>
        )}
      </div>
      {editable && (
        <div className="flex shrink-0 gap-1">
          <button
            onClick={() => openEdit(item)}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
            title="Editar indicacion"
          >
            <Pencil className="h-4 w-4" />
          </button>
          <button
            onClick={() => {
              setError(null);
              if (window.confirm(`Quitar "${item.description}" de las indicaciones?`)) {
                removeMutation.mutate(item.id);
              }
            }}
            disabled={removeMutation.isPending}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
            title="Quitar indicacion"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      )}
    </li>
  );

  return (
    <Card className="p-6">
      <SectionTitle icon={<FileText className="h-5 w-5 text-teal-600" />}>
        Indicaciones del alta
      </SectionTitle>

      <div className="space-y-5">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
              <Pill className="h-4 w-4 text-teal-600" />
              Receta medica
            </p>
            {editable && (
              <ActionButton tone="teal" onClick={() => openCreate('MEDICATION')}>
                <Plus className="h-4 w-4" />
                Medicacion
              </ActionButton>
            )}
          </div>
          {medications.length === 0 ? (
            <p className="text-sm text-slate-400">Sin medicacion indicada.</p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
              {medications.map(row)}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
              <Stethoscope className="h-4 w-4 text-teal-600" />
              Practicas indicadas
            </p>
            {editable && (
              <ActionButton tone="teal" onClick={() => openCreate('PRACTICE')}>
                <Plus className="h-4 w-4" />
                Practica
              </ActionButton>
            )}
          </div>
          {practices.length === 0 ? (
            <p className="text-sm text-slate-400">Sin practicas indicadas.</p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
              {practices.map(row)}
            </ul>
          )}
        </div>

        <FormError message={error} />

        <div className="flex justify-end">
          <ActionButton tone="primary" onClick={print} disabled={printing}>
            <Printer className="h-4 w-4" />
            {printing ? 'Generando...' : 'Imprimir receta e indicaciones'}
          </ActionButton>
        </div>
      </div>

      <Modal
        open={open}
        onClose={closeModal}
        title={
          form.kind === 'MEDICATION'
            ? editing
              ? 'Editar medicacion'
              : 'Medicacion al alta'
            : editing
              ? 'Editar practica indicada'
              : 'Practica indicada al alta'
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          {form.kind === 'PRACTICE' && (
            <Field label="Practica del nomenclador">
              <select
                value={form.practice_id}
                onChange={(event) => setForm({ ...form, practice_id: event.target.value })}
                className={inputClass}
              >
                <option value="">Escribir a mano</option>
                {(catalogQuery.data ?? []).map((practice) => (
                  <option key={practice.id} value={practice.id}>
                    {practice.code} - {practice.name}
                  </option>
                ))}
              </select>
            </Field>
          )}

          <Field
            label={
              form.kind === 'MEDICATION'
                ? 'Medicamento'
                : 'Practica (si no la elegis del nomenclador)'
            }
          >
            <input
              type="text"
              required={form.kind === 'MEDICATION' || !form.practice_id}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              placeholder={form.kind === 'MEDICATION' ? 'Amoxicilina' : 'Ecografia abdominal'}
              className={inputClass}
            />
          </Field>

          {form.kind === 'MEDICATION' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Presentacion">
                <input
                  type="text"
                  value={form.presentation}
                  onChange={(event) => setForm({ ...form, presentation: event.target.value })}
                  placeholder="comprimidos 500 mg"
                  className={inputClass}
                />
              </Field>
              <Field label="Posologia">
                <input
                  type="text"
                  value={form.dosage}
                  onChange={(event) => setForm({ ...form, dosage: event.target.value })}
                  placeholder="1 cada 8 horas"
                  className={inputClass}
                />
              </Field>
              <Field label="Cantidad">
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.quantity}
                  onChange={(event) => setForm({ ...form, quantity: event.target.value })}
                  className={inputClass}
                />
              </Field>
              <Field label="Duracion (dias)">
                <input
                  type="number"
                  min="1"
                  value={form.duration_days}
                  onChange={(event) => setForm({ ...form, duration_days: event.target.value })}
                  className={inputClass}
                />
              </Field>
            </div>
          )}

          <Field label="Profesional que firma">
            <select
              value={form.prescribed_by_id}
              onChange={(event) => setForm({ ...form, prescribed_by_id: event.target.value })}
              className={inputClass}
            >
              <option value="">Sin informar</option>
              {professionals.map((professional) => (
                <option key={professional.id} value={professional.id}>
                  {professional.last_name}, {professional.first_name}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Indicaciones para el paciente">
            <textarea
              rows={2}
              value={form.instructions}
              onChange={(event) => setForm({ ...form, instructions: event.target.value })}
              placeholder="Tomar con las comidas"
              className={inputClass}
            />
          </Field>

          <FormError message={error} />

          <div className="flex justify-end gap-3">
            <ActionButton tone="neutral" onClick={closeModal}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={isSaving}>
              {isSaving ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

export default DischargePrescriptionsCard;
