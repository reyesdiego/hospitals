import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getRegistry } from '@/api/endpoints/registry/registry';
import type {
  HealthPlanCreate,
  HealthPlanRead,
  PayerCreate,
  PayerRead,
} from '@/api/model';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  PageHeader,
  Spinner,
  inputClass,
} from '@/components/ui';
import { apiErrorMessage } from '@/utils/api-error';
import { Building2, ClipboardList, CreditCard, Pencil, Plus, Search, Trash2 } from 'lucide-react';

type PayerForm = { name: string; code: string; tax_id: string };
type PlanForm = { name: string; code: string };

const emptyPayer: PayerForm = { name: '', code: '', tax_id: '' };
const emptyPlan: PlanForm = { name: '', code: '' };

function toPayerPayload(form: PayerForm): PayerCreate {
  return { name: form.name.trim(), code: form.code.trim(), tax_id: form.tax_id.trim() || null };
}

/**
 * Financiadores and the planes that hang from each one. The plan list is the detail of the
 * selected payer, because a plan code only means something inside its payer.
 */
export default function CoveragesPage() {
  const api = getRegistry();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<PayerRead | null>(null);
  const [payerModal, setPayerModal] = useState(false);
  const [editingPayer, setEditingPayer] = useState<PayerRead | null>(null);
  const [payerForm, setPayerForm] = useState<PayerForm>(emptyPayer);
  const [planModal, setPlanModal] = useState(false);
  const [editingPlan, setEditingPlan] = useState<HealthPlanRead | null>(null);
  const [planForm, setPlanForm] = useState<PlanForm>(emptyPlan);
  const [error, setError] = useState<string | null>(null);

  const payersQuery = useQuery({
    queryKey: ['payers'],
    queryFn: () => api.listPayersApiV1PayersGet(),
  });

  const selectedId = selected?.id ?? '';
  const plansQuery = useQuery({
    queryKey: ['health-plans', selectedId],
    queryFn: () => api.listPayerHealthPlansApiV1PayersPayerIdHealthPlansGet(selectedId),
    enabled: selectedId !== '',
  });

  const invalidatePayers = () => queryClient.invalidateQueries({ queryKey: ['payers'] });
  const invalidatePlans = () => queryClient.invalidateQueries({ queryKey: ['health-plans'] });

  const closePayerModal = () => {
    setPayerModal(false);
    setEditingPayer(null);
    setPayerForm(emptyPayer);
    setError(null);
  };

  const closePlanModal = () => {
    setPlanModal(false);
    setEditingPlan(null);
    setPlanForm(emptyPlan);
    setError(null);
  };

  const createPayer = useMutation({
    mutationFn: (data: PayerCreate) => api.createPayerApiV1PayersPost(data),
    onSuccess: () => {
      invalidatePayers();
      closePayerModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar el financiador.')),
  });

  const updatePayer = useMutation({
    mutationFn: ({ payerId, data }: { payerId: string; data: PayerCreate }) =>
      api.updatePayerApiV1PayersPayerIdPut(payerId, data),
    onSuccess: (payer) => {
      invalidatePayers();
      if (selected?.id === payer.id) setSelected(payer);
      closePayerModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar el financiador.')),
  });

  const deletePayer = useMutation({
    mutationFn: (payerId: string) => api.deletePayerApiV1PayersPayerIdDelete(payerId),
    onSuccess: (_data, payerId) => {
      invalidatePayers();
      if (selected?.id === payerId) setSelected(null);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo eliminar el financiador.')),
  });

  const createPlan = useMutation({
    mutationFn: (data: HealthPlanCreate) =>
      api.createHealthPlanApiV1PayersPayerIdHealthPlansPost(selectedId, data),
    onSuccess: () => {
      invalidatePlans();
      closePlanModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar el plan.')),
  });

  const updatePlan = useMutation({
    mutationFn: ({ planId, data }: { planId: string; data: HealthPlanCreate }) =>
      api.updateHealthPlanApiV1HealthPlansHealthPlanIdPut(planId, data),
    onSuccess: () => {
      invalidatePlans();
      closePlanModal();
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar el plan.')),
  });

  const deletePlan = useMutation({
    mutationFn: (planId: string) =>
      api.deleteHealthPlanApiV1HealthPlansHealthPlanIdDelete(planId),
    onSuccess: invalidatePlans,
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo eliminar el plan.')),
  });

  const openCreatePayer = () => {
    setEditingPayer(null);
    setPayerForm(emptyPayer);
    setError(null);
    setPayerModal(true);
  };

  const openEditPayer = (payer: PayerRead) => {
    setEditingPayer(payer);
    setPayerForm({ name: payer.name, code: payer.code, tax_id: payer.tax_id ?? '' });
    setError(null);
    setPayerModal(true);
  };

  const openCreatePlan = () => {
    setEditingPlan(null);
    setPlanForm(emptyPlan);
    setError(null);
    setPlanModal(true);
  };

  const openEditPlan = (plan: HealthPlanRead) => {
    setEditingPlan(plan);
    setPlanForm({ name: plan.name, code: plan.code });
    setError(null);
    setPlanModal(true);
  };

  const submitPayer = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const data = toPayerPayload(payerForm);
    if (editingPayer) {
      updatePayer.mutate({ payerId: editingPayer.id, data });
      return;
    }
    createPayer.mutate(data);
  };

  const submitPlan = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const data: HealthPlanCreate = { name: planForm.name.trim(), code: planForm.code.trim() };
    if (editingPlan) {
      updatePlan.mutate({ planId: editingPlan.id, data });
      return;
    }
    createPlan.mutate(data);
  };

  const term = search.trim().toLowerCase();
  const payers = (payersQuery.data ?? []).filter(
    (payer) =>
      term === '' ||
      payer.name.toLowerCase().includes(term) ||
      payer.code.toLowerCase().includes(term),
  );
  const plans = plansQuery.data ?? [];
  const savingPayer = createPayer.isPending || updatePayer.isPending;
  const savingPlan = createPlan.isPending || updatePlan.isPending;

  return (
    <div>
      <PageHeader
        title="Coberturas"
        subtitle="Financiadores y los planes que se contratan con cada uno"
        action={
          <ActionButton tone="primary" onClick={openCreatePayer}>
            <Plus className="h-4 w-4" />
            Nuevo financiador
          </ActionButton>
        }
      />

      {error && (
        <Card className="mb-4 border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm font-medium text-red-600">{error}</p>
        </Card>
      )}

      {payersQuery.isLoading && <Spinner />}
      {payersQuery.isError && (
        <ErrorState message="No se pudo cargar el catalogo de financiadores." />
      )}

      {payersQuery.data && (
        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="overflow-hidden lg:col-span-3">
            <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-3">
              <Search className="h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Buscar por nombre o codigo"
                className="w-full text-sm outline-none placeholder:text-slate-400"
              />
            </div>

            {payers.length === 0 ? (
              <EmptyState message="No hay financiadores cargados." />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100">
                  <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-5 py-3 text-left font-semibold">Financiador</th>
                      <th className="px-5 py-3 text-left font-semibold">CUIT</th>
                      <th className="px-5 py-3 text-right font-semibold">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {payers.map((payer) => (
                      <tr
                        key={payer.id}
                        onClick={() => setSelected(payer)}
                        className={`cursor-pointer hover:bg-slate-50 ${
                          selected?.id === payer.id ? 'bg-teal-50/60' : ''
                        }`}
                      >
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50">
                              <Building2 className="h-5 w-5 text-teal-600" />
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-slate-800">{payer.name}</p>
                              <p className="text-xs text-slate-400">{payer.code}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4 text-sm text-slate-500">
                          {payer.tax_id ?? 'Sin informar'}
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                openEditPayer(payer);
                              }}
                              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                              title="Editar financiador"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                setError(null);
                                if (window.confirm(`Eliminar financiador "${payer.name}"?`)) {
                                  deletePayer.mutate(payer.id);
                                }
                              }}
                              disabled={deletePayer.isPending}
                              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                              title="Eliminar financiador"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card className="overflow-hidden lg:col-span-2">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
              <div>
                <p className="text-sm font-bold text-slate-800">Planes</p>
                <p className="text-xs text-slate-400">
                  {selected ? selected.name : 'Elija un financiador de la lista'}
                </p>
              </div>
              {selected && (
                <ActionButton tone="teal" onClick={openCreatePlan}>
                  <Plus className="h-4 w-4" />
                  Nuevo plan
                </ActionButton>
              )}
            </div>

            {!selected && <EmptyState message="Sin financiador seleccionado." />}
            {selected && plansQuery.isLoading && <Spinner />}
            {selected && plansQuery.data && plans.length === 0 && (
              <EmptyState message="El financiador no tiene planes cargados." />
            )}
            {selected && plans.length > 0 && (
              <ul className="divide-y divide-slate-100">
                {plans.map((plan) => (
                  <li key={plan.id} className="flex items-center justify-between px-5 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
                        <CreditCard className="h-4 w-4 text-slate-500" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-700">{plan.name}</p>
                        <p className="text-xs text-slate-400">{plan.code}</p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Link
                        to={`/coverages/plans/${plan.id}`}
                        className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                        title="Cartilla de practicas del plan"
                      >
                        <ClipboardList className="h-4 w-4" />
                      </Link>
                      <button
                        onClick={() => openEditPlan(plan)}
                        className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                        title="Editar plan"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => {
                          setError(null);
                          if (window.confirm(`Eliminar plan "${plan.name}"?`)) {
                            deletePlan.mutate(plan.id);
                          }
                        }}
                        disabled={deletePlan.isPending}
                        className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                        title="Eliminar plan"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      <Modal
        open={payerModal}
        onClose={closePayerModal}
        title={editingPayer ? 'Editar financiador' : 'Nuevo financiador'}
      >
        <form onSubmit={submitPayer} className="space-y-4">
          <Field label="Nombre">
            <input
              type="text"
              required
              value={payerForm.name}
              onChange={(event) => setPayerForm({ ...payerForm, name: event.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Codigo">
            <input
              type="text"
              required
              value={payerForm.code}
              onChange={(event) =>
                setPayerForm({ ...payerForm, code: event.target.value.toUpperCase() })
              }
              className={inputClass}
            />
          </Field>
          <Field label="CUIT">
            <input
              type="text"
              value={payerForm.tax_id}
              onChange={(event) => setPayerForm({ ...payerForm, tax_id: event.target.value })}
              placeholder="30-12345678-9"
              className={inputClass}
            />
          </Field>

          <FormError message={error} />

          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={closePayerModal}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={savingPayer}>
              {savingPayer ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={planModal}
        onClose={closePlanModal}
        title={editingPlan ? 'Editar plan' : `Nuevo plan de ${selected?.name ?? ''}`}
      >
        <form onSubmit={submitPlan} className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-xs text-slate-500">
            El plan queda bajo {selected?.name ?? 'el financiador'} y no puede moverse a otro:
            las coberturas y los aranceles ya pactados cuelgan de el.
          </p>
          <Field label="Nombre">
            <input
              type="text"
              required
              value={planForm.name}
              onChange={(event) => setPlanForm({ ...planForm, name: event.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Codigo">
            <input
              type="text"
              required
              value={planForm.code}
              onChange={(event) =>
                setPlanForm({ ...planForm, code: event.target.value.toUpperCase() })
              }
              className={inputClass}
            />
          </Field>

          <FormError message={error} />

          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={closePlanModal}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={savingPlan}>
              {savingPlan ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
