/**
 * Mock de inicio de sesion: los mismos cuatro usuarios que siembra la API.
 *
 * El token es opaco y de mentira, pero lleva el rol para que el adaptador aplique las
 * reglas que dependen de quien opera (por ejemplo, el candado posterior al alta medica).
 * Los permisos por endpoint los valida la API real; aca solo se sirve la sesion.
 */
import type { Permission, UserRead, UserRole } from './model';

type Ok = { kind: 'ok'; data: unknown; status: number };
type Err = { kind: 'error'; status: number; detail: string };
export type AuthResult = Ok | Err;

const ok = (data: unknown, status = 200): Ok => ({ kind: 'ok', data, status });
const err = (status: number, detail: string): Err => ({ kind: 'error', status, detail });

const PASSWORD = 'Hospital.2026';

const PERMISSIONS: Record<UserRole, Permission[]> = {
  ADMIN: [
    'ADMISSION',
    'BED_CLEANING',
    'BED_MANAGEMENT',
    'BILLING',
    'CATALOG',
    'HOSPITALIZATION',
    'USER_ADMIN',
  ],
  RECEPTIONIST: ['ADMISSION'],
  DOCTOR: ['HOSPITALIZATION'],
  NURSE: ['BED_CLEANING'],
};

const USERS: UserRead[] = [
  {
    id: 'usr-admin',
    email: 'admin@hospital.local',
    full_name: 'Administracion del sistema',
    role: 'ADMIN',
    is_active: true,
    last_login_at: null,
    created_at: '2026-01-01T08:00:00Z',
  },
  {
    id: 'usr-recepcion',
    email: 'recepcion@hospital.local',
    full_name: 'Recepcion',
    role: 'RECEPTIONIST',
    is_active: true,
    last_login_at: null,
    created_at: '2026-01-01T08:00:00Z',
  },
  {
    id: 'usr-medico',
    email: 'medico@hospital.local',
    full_name: 'Profesional medico',
    role: 'DOCTOR',
    is_active: true,
    last_login_at: null,
    created_at: '2026-01-01T08:00:00Z',
  },
  {
    id: 'usr-enfermeria',
    email: 'enfermeria@hospital.local',
    full_name: 'Enfermeria',
    role: 'NURSE',
    is_active: true,
    last_login_at: null,
    created_at: '2026-01-01T08:00:00Z',
  },
];

const tokenFor = (user: UserRead) => `mock-token.${user.role}.${user.id}`;

const uuid = () => `usr-${Math.random().toString(36).slice(2, 10)}`;

const emailOf = (body: Record<string, unknown>) =>
  String(body.email ?? '').trim().toLowerCase();

const userOfToken = (token: string | undefined): UserRead | null => {
  const id = (token ?? '').split('.')[2];
  return USERS.find((user) => user.id === id) ?? null;
};

/** Rol de quien hace el pedido, leido del token del header. */
export function roleFromAuthorization(authorization: string | undefined): string | undefined {
  const [scheme, token] = (authorization ?? '').split(' ');
  if (scheme?.toLowerCase() !== 'bearer') return undefined;
  return userOfToken(token)?.role;
}

export function handleAuthRequest(
  url: string,
  method: string,
  body: Record<string, unknown>,
  authorization: string | undefined,
): AuthResult | null {
  if (url === '/api/v1/auth/login' && method === 'post') {
    const email = String(body.email ?? '').trim().toLowerCase();
    const user = USERS.find((item) => item.email === email);
    if (!user || body.password !== PASSWORD) {
      return err(401, 'Usuario o contraseña incorrectos');
    }
    const expires = new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString();
    return ok({
      token: tokenFor(user),
      expires_at: expires,
      user: { ...user, last_login_at: new Date().toISOString() },
      permissions: PERMISSIONS[user.role],
    });
  }

  if (url === '/api/v1/auth/logout' && method === 'post') {
    return ok(undefined, 204);
  }

  if (url === '/api/v1/auth/me' && method === 'get') {
    const [, token] = (authorization ?? '').split(' ');
    const user = userOfToken(token);
    if (!user) return err(401, 'Sesión inválida o vencida');
    return ok({ user, permissions: PERMISSIONS[user.role] });
  }

  if (url === '/api/v1/users' && method === 'get') {
    return ok(USERS);
  }

  if (url === '/api/v1/users' && method === 'post') {
    const email = emailOf(body);
    if (USERS.some((user) => user.email === email)) {
      return err(409, 'Ya existe un usuario con ese correo');
    }
    const user: UserRead = {
      id: uuid(),
      email,
      full_name: String(body.full_name ?? '').trim(),
      role: body.role as UserRole,
      is_active: body.is_active !== false,
      last_login_at: null,
      created_at: new Date().toISOString(),
    };
    USERS.push(user);
    return ok(user, 201);
  }

  const userMatch = url.match(/^\/api\/v1\/users\/([^/]+)$/);
  if (userMatch && method === 'put') {
    const user = USERS.find((item) => item.id === userMatch[1]);
    if (!user) return err(404, 'Usuario inexistente');
    const email = emailOf(body);
    if (USERS.some((item) => item.id !== user.id && item.email === email)) {
      return err(409, 'Ya existe un usuario con ese correo');
    }
    user.email = email;
    user.full_name = String(body.full_name ?? user.full_name).trim();
    user.role = body.role as UserRole;
    user.is_active = body.is_active !== false;
    return ok(user);
  }

  return null;
}
