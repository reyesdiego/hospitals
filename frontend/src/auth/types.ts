export type Role = 'admin' | 'doctor' | 'nurse' | 'receptionist' | 'patient';

export type AuthUser = {
  name: string;
  role: Role;
  email: string;
};

export const ROLE_LABELS: Record<Role, string> = {
  admin: 'Administrador',
  doctor: 'Medico',
  nurse: 'Enfermeria',
  receptionist: 'Recepcion',
  patient: 'Paciente',
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  admin: 'Acceso completo al sistema',
  doctor: 'Gestion clinica y hospitalizaciones',
  nurse: 'Control de camas y pacientes',
  receptionist: 'Registro de pacientes y admision',
  patient: 'Consulta de tu informacion',
};
