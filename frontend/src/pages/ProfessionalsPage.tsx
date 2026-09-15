import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type {
  ProfessionalCreate,
  ProfessionalRead,
  SpecialtyCreate,
  SpecialtyRead,
} from '@/api/model';
import { PageHeader, Card, Spinner, ErrorState, EmptyState } from '@/components/ui';
import Modal from '@/components/Modal';
import { Pencil, Plus, Stethoscope, Trash2, UserRoundPlus } from 'lucide-react';

const DOC_TYPES = ['DNI', 'NIE', 'PASSPORT', 'CIF'];

type Tab = 'professionals' | 'specialties';
type ProfessionalForm = ProfessionalCreate;
type SpecialtyForm = SpecialtyCreate;

const emptyProfessionalForm: ProfessionalForm = {
  first_name: '',
  last_name: '',
  document_type: 'DNI',
  document_number: '',
  email: null,
  phone: null,
  specialties: [],
};
const emptySpecialtyForm: SpecialtyForm = { name: '', code: '' };
const professionalSpecialties = (professional: ProfessionalRead) => professional.specialties ?? [];

export default function ProfessionalsPage() {
  const api = getDefault();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('professionals');
  const [professionalModalOpen, setProfessionalModalOpen] = useState(false);
  const [specialtyModalOpen, setSpecialtyModalOpen] = useState(false);
  const [editingProfessional, setEditingProfessional] = useState<ProfessionalRead | null>(null);
  const [editingSpecialty, setEditingSpecialty] = useState<SpecialtyRead | null>(null);
  const [professionalForm, setProfessionalForm] =
    useState<ProfessionalForm>(emptyProfessionalForm);
  const [specialtyForm, setSpecialtyForm] = useState<SpecialtyForm>(emptySpecialtyForm);

  const professionalsQuery = useQuery({
    queryKey: ['professionals'],
    queryFn: () => api.listProfessionalsApiV1ProfessionalsGet(),
  });
  const specialtiesQuery = useQuery({
    queryKey: ['specialties'],
    queryFn: () => api.listSpecialtiesApiV1SpecialtiesGet(),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['professionals'] });
    queryClient.invalidateQueries({ queryKey: ['specialties'] });
  };

  const createProfessional = useMutation({
    mutationFn: (data: ProfessionalCreate) => api.createProfessionalApiV1ProfessionalsPost(data),
    onSuccess: () => {
      invalidate();
      closeProfessionalModal();
    },
  });
  const updateProfessional = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProfessionalCreate }) =>
      api.updateProfessionalApiV1ProfessionalsProfessionalIdPut(id, data),
    onSuccess: () => {
      invalidate();
      closeProfessionalModal();
    },
  });
  const deleteProfessional = useMutation({
    mutationFn: (id: string) => api.deleteProfessionalApiV1ProfessionalsProfessionalIdDelete(id),
    onSuccess: invalidate,
  });
  const createSpecialty = useMutation({
    mutationFn: (data: SpecialtyCreate) => api.createSpecialtyApiV1SpecialtiesPost(data),
    onSuccess: () => {
      invalidate();
      closeSpecialtyModal();
    },
  });
  const updateSpecialty = useMutation({
    mutationFn: ({ id, data }: { id: string; data: SpecialtyCreate }) =>
      api.updateSpecialtyApiV1SpecialtiesSpecialtyIdPut(id, data),
    onSuccess: () => {
      invalidate();
      closeSpecialtyModal();
    },
  });
  const deleteSpecialty = useMutation({
    mutationFn: (id: string) => api.deleteSpecialtyApiV1SpecialtiesSpecialtyIdDelete(id),
    onSuccess: invalidate,
  });

  const closeProfessionalModal = () => {
    setProfessionalModalOpen(false);
    setEditingProfessional(null);
    setProfessionalForm(emptyProfessionalForm);
  };

  const closeSpecialtyModal = () => {
    setSpecialtyModalOpen(false);
    setEditingSpecialty(null);
    setSpecialtyForm(emptySpecialtyForm);
  };

  const openProfessionalCreate = () => {
    setEditingProfessional(null);
    setProfessionalForm(emptyProfessionalForm);
    setProfessionalModalOpen(true);
  };

  const openProfessionalEdit = (professional: ProfessionalRead) => {
    setEditingProfessional(professional);
    setProfessionalForm({
      first_name: professional.first_name,
      last_name: professional.last_name,
      document_type: professional.document_type,
      document_number: professional.document_number,
      email: professional.email,
      phone: professional.phone,
      specialties: professionalSpecialties(professional).map((item) => ({
        specialty_id: item.specialty_id,
        license_number: item.license_number,
      })),
    });
    setProfessionalModalOpen(true);
  };

  const openSpecialtyEdit = (specialty: SpecialtyRead) => {
    setEditingSpecialty(specialty);
    setSpecialtyForm({ name: specialty.name, code: specialty.code });
    setSpecialtyModalOpen(true);
  };

  const submitProfessional = (event: React.FormEvent) => {
    event.preventDefault();
    if (editingProfessional) {
      updateProfessional.mutate({ id: editingProfessional.id, data: professionalForm });
      return;
    }
    createProfessional.mutate(professionalForm);
  };

  const submitSpecialty = (event: React.FormEvent) => {
    event.preventDefault();
    if (editingSpecialty) {
      updateSpecialty.mutate({ id: editingSpecialty.id, data: specialtyForm });
      return;
    }
    createSpecialty.mutate(specialtyForm);
  };

  const addSpecialtyRow = () => {
    const firstSpecialty = specialtiesQuery.data?.[0];
    if (!firstSpecialty) return;
    setProfessionalForm({
      ...professionalForm,
      specialties: [
        ...(professionalForm.specialties ?? []),
        { specialty_id: firstSpecialty.id, license_number: '' },
      ],
    });
  };

  const professionalSaving = createProfessional.isPending || updateProfessional.isPending;
  const specialtySaving = createSpecialty.isPending || updateSpecialty.isPending;
  const professionals = professionalsQuery.data ?? [];
  const specialties = specialtiesQuery.data ?? [];
  const professionalFormSpecialties = professionalForm.specialties ?? [];

  return (
    <div>
      <PageHeader
        title="Profesionales"
        subtitle="Gestion de profesionales, especialidades y matriculas"
        action={
          tab === 'professionals' ? (
            <button
              onClick={openProfessionalCreate}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
            >
              <UserRoundPlus className="h-4 w-4" />
              Nuevo profesional
            </button>
          ) : (
            <button
              onClick={() => setSpecialtyModalOpen(true)}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:shadow-lg"
            >
              <Plus className="h-4 w-4" />
              Nueva especialidad
            </button>
          )
        }
      />

      <div className="mb-5 inline-flex rounded-lg border border-slate-200 bg-white p-1">
        {[
          ['professionals', 'Profesionales'],
          ['specialties', 'Especialidades'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key as Tab)}
            className={`rounded-md px-4 py-2 text-sm font-semibold transition-colors ${
              tab === key ? 'bg-teal-50 text-teal-700' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {(professionalsQuery.isLoading || specialtiesQuery.isLoading) && <Spinner />}
      {(professionalsQuery.isError || specialtiesQuery.isError) && (
        <ErrorState message="No se pudo cargar la informacion." />
      )}

      {tab === 'professionals' && professionalsQuery.data && (
        <Card className="overflow-hidden">
          {professionals.length === 0 ? (
            <EmptyState message="No hay profesionales registrados." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Profesional
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Documento
                    </th>
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Especialidades
                    </th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-slate-500">
                      Acciones
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {professionals.map((professional) => (
                    <tr key={professional.id} className="hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <p className="text-sm font-semibold text-slate-800">
                          {professional.first_name} {professional.last_name}
                        </p>
                        <p className="text-xs text-slate-400">
                          {[professional.email, professional.phone].filter(Boolean).join(' · ') ||
                            'Sin contacto'}
                        </p>
                      </td>
                      <td className="px-5 py-4 text-sm text-slate-500">
                        {professional.document_type} - {professional.document_number}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap gap-2">
                          {professionalSpecialties(professional).length === 0 ? (
                            <span className="text-sm text-slate-400">Sin especialidades</span>
                          ) : (
                            professionalSpecialties(professional).map((item) => (
                              <span
                                key={item.id}
                                className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600"
                              >
                                {item.specialty.name} · {item.license_number}
                              </span>
                            ))
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => openProfessionalEdit(professional)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Editar profesional"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              if (window.confirm('Eliminar profesional?')) {
                                deleteProfessional.mutate(professional.id);
                              }
                            }}
                            disabled={deleteProfessional.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                            title="Eliminar profesional"
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
      )}

      {tab === 'specialties' && specialtiesQuery.data && (
        <Card className="overflow-hidden">
          {specialties.length === 0 ? (
            <EmptyState message="No hay especialidades registradas." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <tbody className="divide-y divide-slate-100 bg-white">
                  {specialties.map((specialty) => (
                    <tr key={specialty.id} className="hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50">
                            <Stethoscope className="h-5 w-5 text-teal-600" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-slate-800">{specialty.name}</p>
                            <p className="text-xs text-slate-400">{specialty.code}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => openSpecialtyEdit(specialty)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Editar especialidad"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              if (window.confirm(`Eliminar especialidad "${specialty.name}"?`)) {
                                deleteSpecialty.mutate(specialty.id);
                              }
                            }}
                            disabled={deleteSpecialty.isPending}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                            title="Eliminar especialidad"
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
      )}

      <Modal
        open={professionalModalOpen}
        onClose={closeProfessionalModal}
        title={editingProfessional ? 'Editar profesional' : 'Nuevo profesional'}
      >
        <form onSubmit={submitProfessional} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input label="Nombre" value={professionalForm.first_name} onChange={(value) => setProfessionalForm({ ...professionalForm, first_name: value })} />
            <Input label="Apellidos" value={professionalForm.last_name} onChange={(value) => setProfessionalForm({ ...professionalForm, last_name: value })} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-600">Tipo doc.</span>
              <select
                value={professionalForm.document_type}
                onChange={(event) =>
                  setProfessionalForm({ ...professionalForm, document_type: event.target.value })
                }
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              >
                {DOC_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <Input label="Numero doc." value={professionalForm.document_number} onChange={(value) => setProfessionalForm({ ...professionalForm, document_number: value })} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Email" type="email" required={false} value={professionalForm.email ?? ''} onChange={(value) => setProfessionalForm({ ...professionalForm, email: value || null })} />
            <Input label="Telefono" required={false} value={professionalForm.phone ?? ''} onChange={(value) => setProfessionalForm({ ...professionalForm, phone: value || null })} />
          </div>

          <div className="rounded-lg border border-slate-200 p-3">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-700">Especialidades y matriculas</p>
              <button
                type="button"
                onClick={addSpecialtyRow}
                disabled={specialties.length === 0}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                Agregar
              </button>
            </div>
            {professionalFormSpecialties.length === 0 ? (
              <p className="text-sm text-slate-400">Sin especialidades asignadas.</p>
            ) : (
              <div className="space-y-3">
                {professionalFormSpecialties.map((item, index) => (
                  <div key={index} className="grid grid-cols-[1fr_1fr_auto] gap-3">
                    <select
                      value={item.specialty_id}
                      onChange={(event) => {
                        const rows = [...professionalFormSpecialties];
                        rows[index] = { ...item, specialty_id: event.target.value };
                        setProfessionalForm({ ...professionalForm, specialties: rows });
                      }}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
                    >
                      {specialties.map((specialty) => (
                        <option key={specialty.id} value={specialty.id}>
                          {specialty.name}
                        </option>
                      ))}
                    </select>
                    <input
                      required
                      value={item.license_number}
                      onChange={(event) => {
                        const rows = [...professionalFormSpecialties];
                        rows[index] = { ...item, license_number: event.target.value };
                        setProfessionalForm({ ...professionalForm, specialties: rows });
                      }}
                      placeholder="Matricula"
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setProfessionalForm({
                          ...professionalForm,
                          specialties: professionalFormSpecialties.filter((_, i) => i !== index),
                        })
                      }
                      className="rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-600"
                      title="Quitar especialidad"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {(createProfessional.isError || updateProfessional.isError) && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al guardar el profesional.
            </p>
          )}
          <ModalActions disabled={professionalSaving} onCancel={closeProfessionalModal} />
        </form>
      </Modal>

      <Modal
        open={specialtyModalOpen}
        onClose={closeSpecialtyModal}
        title={editingSpecialty ? 'Editar especialidad' : 'Nueva especialidad'}
      >
        <form onSubmit={submitSpecialty} className="space-y-4">
          <Input label="Nombre" value={specialtyForm.name} onChange={(value) => setSpecialtyForm({ ...specialtyForm, name: value })} />
          <Input label="Codigo" value={specialtyForm.code} onChange={(value) => setSpecialtyForm({ ...specialtyForm, code: value.toUpperCase() })} />
          {(createSpecialty.isError || updateSpecialty.isError) && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              Error al guardar la especialidad.
            </p>
          )}
          <ModalActions disabled={specialtySaving} onCancel={closeSpecialtyModal} />
        </form>
      </Modal>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  type = 'text',
  required = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-600">{label}</span>
      <input
        type={type}
        required={required}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
      />
    </label>
  );
}

function ModalActions({ disabled, onCancel }: { disabled: boolean; onCancel: () => void }) {
  return (
    <div className="flex justify-end gap-3 pt-2">
      <button
        type="button"
        onClick={onCancel}
        className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
      >
        Cancelar
      </button>
      <button
        type="submit"
        disabled={disabled}
        className="rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-md disabled:opacity-50"
      >
        {disabled ? 'Guardando...' : 'Guardar'}
      </button>
    </div>
  );
}
