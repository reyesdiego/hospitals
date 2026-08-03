import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { FacilityCreate } from '@/api/model';
import { PageHeader, Card } from '@/components/ui';
import Modal from '@/components/Modal';
import { Building2, Plus, CheckCircle2 } from 'lucide-react';

export default function FacilitiesPage() {
  const api = getDefault();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [created, setCreated] = useState<{ name: string; code: string } | null>(null);

  const [form, setForm] = useState<FacilityCreate>({ name: '', code: '' });

  const createMutation = useMutation({
    mutationFn: (data: FacilityCreate) => api.createFacilityApiV1FacilitiesPost(data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['facilities'] });
      setCreated({ name: data.name, code: data.code });
      setForm({ name: '', code: '' });
      setModalOpen(false);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(form);
  };

  return (
    <div>
      <PageHeader
        title="Centros sanitarios"
        subtitle="Alta de centros y instalaciones hospitalarias"
        action={
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
          >
            <Plus className="h-4 w-4" />
            Nuevo centro
          </button>
        }
      />

      {created && (
        <Card className="mb-6 flex items-center gap-3 border-emerald-200 bg-emerald-50 p-4">
          <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          <p className="text-sm font-medium text-emerald-700">
            Centro "{created.name}" ({created.code}) creado correctamente.
          </p>
        </Card>
      )}

      <Card className="p-8">
        <div className="flex flex-col items-center justify-center text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-teal-50">
            <Building2 className="h-8 w-8 text-teal-600" />
          </div>
          <h3 className="mb-2 text-lg font-bold text-slate-700">Gestion de centros</h3>
          <p className="mb-4 max-w-md text-sm text-slate-500">
            Crea nuevos centros sanitarios para dar de alta camas y gestionar
            hospitalizaciones. Cada centro se identifica por su nombre y codigo unico.
          </p>
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 rounded-lg border border-teal-200 bg-teal-50 px-4 py-2.5 text-sm font-semibold text-teal-700 transition-all hover:bg-teal-100"
          >
            <Plus className="h-4 w-4" />
            Crear centro
          </button>
        </div>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Nuevo centro sanitario">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Nombre del centro
            </label>
            <input
              type="text"
              required
              placeholder="Hospital General Central"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">
              Codigo unico
            </label>
            <input
              type="text"
              required
              placeholder="HGC"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>

          {createMutation.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al crear el centro.
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setModalOpen(false)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
            >
              {createMutation.isPending ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
