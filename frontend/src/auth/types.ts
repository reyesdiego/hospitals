import type { Permission, UserRead, UserRole } from '@/api/model';

export type { Permission, UserRole };

/** Sesion abierta en el navegador. */
export type AuthUser = UserRead & { permissions: Permission[] };

export const ROLE_LABELS: Record<UserRole, string> = {
  ADMIN: 'Administracion',
  RECEPTIONIST: 'Recepcion',
  DOCTOR: 'Profesional medico',
  NURSE: 'Enfermeria',
};

export const ROLE_DESCRIPTIONS: Record<UserRole, string> = {
  ADMIN: 'Acceso completo al sistema',
  RECEPTIONIST: 'Registro de pacientes, coberturas y admision',
  DOCTOR: 'Gestion clinica de la internacion',
  NURSE: 'Higiene y disponibilidad de camas',
};

export const PERMISSION_LABELS: Record<Permission, string> = {
  ADMISSION: 'Admision',
  HOSPITALIZATION: 'Internacion',
  BED_CLEANING: 'Limpieza de camas',
  NURSING_TASKS: 'Tareas de enfermeria',
  BED_MANAGEMENT: 'Gestion de camas',
  BILLING: 'Cuenta y facturacion',
  CATALOG: 'Catalogos',
  USER_ADMIN: 'Usuarios',
};
