import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getAuth } from '@/api/endpoints/auth/auth';
import type { UserCreate, UserRead, UserRole, UserUpdate } from '@/api/model';
import { useAuth } from '@/auth/AuthContext';
import { PERMISSION_LABELS, ROLE_DESCRIPTIONS, ROLE_LABELS } from '@/auth/types';
import Modal from '@/components/Modal';
import {
  ActionButton,
  Badge,
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
import { formatDateTime } from '@/utils/format';
import { KeyRound, Pencil, Plus, ShieldCheck, UserPlus } from 'lucide-react';

/** Lo que habilita cada rol, para que el alta no sea a ciegas. */
const ROLE_PERMISSIONS: Record<UserRole, (keyof typeof PERMISSION_LABELS)[]> = {
  ADMIN: [
    'ADMISSION',
    'HOSPITALIZATION',
    'NURSING_TASKS',
    'BED_CLEANING',
    'BED_MANAGEMENT',
    'BILLING',
    'CATALOG',
    'USER_ADMIN',
  ],
  RECEPTIONIST: ['ADMISSION'],
  DOCTOR: ['HOSPITALIZATION'],
  NURSE: ['NURSING_TASKS', 'BED_CLEANING'],
};

const ROLES = Object.keys(ROLE_LABELS) as UserRole[];

type UserForm = {
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  password: string;
};

const emptyForm: UserForm = {
  email: '',
  full_name: '',
  role: 'RECEPTIONIST',
  is_active: true,
  password: '',
};

const STATUS_COLORS = {
  active: 'bg-emerald-50 text-emerald-700',
  inactive: 'bg-slate-100 text-slate-600',
};

export default function UsersPage() {
  const api = getAuth();
  const queryClient = useQueryClient();
  const { user: current } = useAuth();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<UserRead | null>(null);
  const [form, setForm] = useState<UserForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: () => api.listUsersApiV1UsersGet(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['users'] });

  const closeModal = () => {
    setOpen(false);
    setEditing(null);
    setForm(emptyForm);
    setError(null);
  };

  const createMutation = useMutation({
    mutationFn: (data: UserCreate) => api.createUserApiV1UsersPost(data),
    onSuccess: (user) => {
      invalidate();
      closeModal();
      setNotice(`Usuario ${user.email} creado. Pasale la contrasena para que la cambie.`);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo crear el usuario.')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: UserUpdate }) =>
      api.updateUserApiV1UsersUserIdPut(userId, data),
    onSuccess: (user) => {
      invalidate();
      closeModal();
      setNotice(`Usuario ${user.email} actualizado.`);
    },
    onError: (err) => setError(apiErrorMessage(err, 'No se pudo guardar el usuario.')),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setError(null);
    setNotice(null);
    setOpen(true);
  };

  const openEdit = (user: UserRead) => {
    setEditing(user);
    setForm({
      email: user.email,
      full_name: user.full_name,
      role: user.role,
      is_active: user.is_active,
      password: '',
    });
    setError(null);
    setNotice(null);
    setOpen(true);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const base = {
      email: form.email.trim().toLowerCase(),
      full_name: form.full_name.trim(),
      role: form.role,
      is_active: form.is_active,
    };
    if (editing) {
      // Contrasena vacia: se deja la que tenia.
      updateMutation.mutate({
        userId: editing.id,
        data: { ...base, password: form.password.trim() || null },
      });
      return;
    }
    createMutation.mutate({ ...base, password: form.password });
  };

  const users = usersQuery.data ?? [];
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const editingSelf = editing?.id === current?.id;
  const roleChanges = editing !== null && editing.role !== form.role;
  const disablingSelf = editingSelf && !form.is_active;

  return (
    <div>
      <PageHeader
        title="Usuarios"
        subtitle="Quien entra al sistema y que puede hacer"
        action={
          <ActionButton tone="primary" onClick={openCreate}>
            <UserPlus className="h-4 w-4" />
            Nuevo usuario
          </ActionButton>
        }
      />

      {notice && (
        <Card className="mb-4 border-teal-200 bg-teal-50 px-4 py-3">
          <p className="text-sm font-medium text-teal-700">{notice}</p>
        </Card>
      )}

      {usersQuery.isLoading && <Spinner />}
      {usersQuery.isError && <ErrorState message="No se pudo cargar la lista de usuarios." />}

      {usersQuery.data && (
        <Card className="overflow-hidden">
          {users.length === 0 ? (
            <EmptyState message="No hay usuarios cargados." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-5 py-3 text-left font-semibold">Usuario</th>
                    <th className="px-5 py-3 text-left font-semibold">Rol</th>
                    <th className="px-5 py-3 text-left font-semibold">Permisos</th>
                    <th className="px-5 py-3 text-left font-semibold">Ultimo ingreso</th>
                    <th className="px-5 py-3 text-right font-semibold">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {users.map((user) => (
                    <tr key={user.id} className="hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-cyan-600 text-xs font-bold text-white">
                            {user.full_name.slice(0, 2).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-slate-800">
                              {user.full_name}
                              {user.id === current?.id && (
                                <span className="ml-2 text-xs font-medium text-teal-600">vos</span>
                              )}
                            </p>
                            <p className="text-xs text-slate-400">{user.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <Badge
                          status={ROLE_LABELS[user.role]}
                          color={user.is_active ? STATUS_COLORS.active : STATUS_COLORS.inactive}
                        />
                        {!user.is_active && (
                          <p className="mt-1 text-xs text-slate-400">Dado de baja</p>
                        )}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap gap-1">
                          {ROLE_PERMISSIONS[user.role].map((permission) => (
                            <span
                              key={permission}
                              className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                            >
                              {PERMISSION_LABELS[permission]}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-sm text-slate-500">
                        {user.last_login_at ? formatDateTime(user.last_login_at) : 'Nunca'}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex justify-end">
                          <button
                            onClick={() => openEdit(user)}
                            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-teal-50 hover:text-teal-700"
                            title="Editar usuario"
                          >
                            <Pencil className="h-4 w-4" />
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
        open={open}
        onClose={closeModal}
        title={editing ? `Editar ${editing.full_name}` : 'Nuevo usuario'}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Nombre y apellido">
            <input
              type="text"
              required
              value={form.full_name}
              onChange={(event) => setForm({ ...form, full_name: event.target.value })}
              className={inputClass}
            />
          </Field>

          <Field label="Correo">
            <input
              type="email"
              required
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
              placeholder="usuario@hospital.local"
              className={inputClass}
            />
          </Field>

          <Field label="Rol">
            <select
              value={form.role}
              onChange={(event) => setForm({ ...form, role: event.target.value as UserRole })}
              className={inputClass}
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {ROLE_LABELS[role]}
                </option>
              ))}
            </select>
            <p className="mt-1.5 text-xs text-slate-500">{ROLE_DESCRIPTIONS[form.role]}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {ROLE_PERMISSIONS[form.role].map((permission) => (
                <span
                  key={permission}
                  className="inline-flex items-center gap-1 rounded-md bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-700"
                >
                  <ShieldCheck className="h-3 w-3" />
                  {PERMISSION_LABELS[permission]}
                </span>
              ))}
            </div>
          </Field>

          <Field label={editing ? 'Nueva contrasena (vacia: se deja la actual)' : 'Contrasena'}>
            <input
              type="password"
              required={!editing}
              minLength={8}
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              placeholder={editing ? 'Sin cambios' : 'Al menos 8 caracteres'}
              className={inputClass}
            />
          </Field>

          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
              className="h-4 w-4 rounded border-slate-300"
            />
            Usuario habilitado
          </label>

          {(roleChanges || (editing && form.password.trim()) || disablingSelf) && (
            <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-4 py-3 text-xs text-amber-800">
              <KeyRound className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                {disablingSelf
                  ? 'Te estas dando de baja a vos mismo: vas a perder el acceso al guardar.'
                  : 'Cambiar el rol o la contrasena cierra las sesiones abiertas de este usuario.'}
              </span>
            </p>
          )}

          <FormError message={error} />

          <div className="flex justify-end gap-3 pt-2">
            <ActionButton tone="neutral" onClick={closeModal}>
              Cancelar
            </ActionButton>
            <ActionButton tone="primary" type="submit" disabled={isSaving}>
              <Plus className="h-4 w-4" />
              {isSaving ? 'Guardando...' : 'Guardar'}
            </ActionButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
