import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { type Role, ROLE_LABELS, ROLE_DESCRIPTIONS } from '@/auth/types';
import { HeartPulse, ArrowRight, ShieldCheck, UserCog, Stethoscope, HeartPulse as NurseIcon, User } from 'lucide-react';

const ROLE_ICONS: Record<Role, typeof HeartPulse> = {
  admin: ShieldCheck,
  doctor: Stethoscope,
  nurse: NurseIcon,
  receptionist: UserCog,
  patient: User,
};

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRole || !name || !email) return;
    login(selectedRole, name, email);
    navigate('/dashboard');
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-900 lg:flex-row">
      {/* Left panel - branding */}
      <div className="relative flex items-center justify-center overflow-hidden bg-gradient-to-br from-slate-900 via-teal-950 to-cyan-950 p-8 lg:w-1/2 lg:p-16">
        <div className="absolute -left-20 -top-20 h-72 w-72 rounded-full bg-teal-500/10 blur-3xl" />
        <div className="absolute -bottom-20 -right-10 h-96 w-96 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative z-10 max-w-md">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-400 to-cyan-600 shadow-2xl shadow-cyan-900/40">
              <HeartPulse className="h-8 w-8 text-white" strokeWidth={2.2} />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">HospitaLink</h1>
              <p className="text-sm text-teal-300">Sistema de hospitalizacion</p>
            </div>
          </div>
          <h2 className="mb-4 text-3xl font-bold leading-tight text-white lg:text-4xl">
            Gestion clinica moderna y eficiente
          </h2>
          <p className="text-lg leading-relaxed text-slate-300">
            Administra pacientes, camas, hospitalizaciones y asignaciones desde una
            plataforma unificada. Disenada para profesionales sanitarios.
          </p>
          <div className="mt-10 space-y-3">
            {[
              'Control en tiempo real de camas y hospitalizaciones',
              'Registro y seguimiento de pacientes',
              'Asignacion inteligente de recursos',
            ].map((feat) => (
              <div key={feat} className="flex items-center gap-3 text-slate-300">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-teal-500/20">
                  <ArrowRight className="h-3.5 w-3.5 text-teal-400" />
                </div>
                {feat}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel - login form */}
      <div className="flex items-center justify-center bg-slate-50 p-8 lg:w-1/2 lg:p-16">
        <div className="w-full max-w-md">
          <h2 className="mb-2 text-2xl font-bold text-slate-800">Iniciar sesion</h2>
          <p className="mb-8 text-slate-500">Selecciona tu perfil para continuar</p>

          {/* Role selection */}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {(Object.keys(ROLE_LABELS) as Role[]).map((role) => {
              const Icon = ROLE_ICONS[role];
              const active = selectedRole === role;
              return (
                <button
                  key={role}
                  type="button"
                  onClick={() => setSelectedRole(role)}
                  className={`flex flex-col items-center gap-2 rounded-xl border-2 p-4 transition-all duration-200 ${
                    active
                      ? 'border-teal-500 bg-teal-50 shadow-md shadow-teal-100'
                      : 'border-slate-200 bg-white hover:border-teal-200 hover:bg-slate-50'
                  }`}
                >
                  <Icon
                    className={`h-6 w-6 ${active ? 'text-teal-600' : 'text-slate-400'}`}
                    strokeWidth={2}
                  />
                  <span
                    className={`text-xs font-semibold ${
                      active ? 'text-teal-700' : 'text-slate-500'
                    }`}
                  >
                    {ROLE_LABELS[role]}
                  </span>
                </button>
              );
            })}
          </div>

          {selectedRole && (
            <p className="mb-6 rounded-lg bg-teal-50 px-4 py-2.5 text-sm text-teal-700">
              {ROLE_DESCRIPTIONS[selectedRole]}
            </p>
          )}

          {/* Login form */}
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">
                Nombre completo
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Dr. Ana Lopez"
                className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-slate-800 outline-none transition-all focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
                required
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">
                Correo electronico
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ana.lopez@hospital.es"
                className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-slate-800 outline-none transition-all focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
                required
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">
                Contrasena
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-slate-800 outline-none transition-all focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
              />
            </div>
            <button
              type="submit"
              disabled={!selectedRole || !name || !email}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-3 font-semibold text-white shadow-lg shadow-cyan-900/20 transition-all duration-200 hover:shadow-xl hover:shadow-cyan-900/30 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Acceder
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-slate-400">
            Entorno de demostracion - cualquier credencial es valida
          </p>
        </div>
      </div>
    </div>
  );
}
