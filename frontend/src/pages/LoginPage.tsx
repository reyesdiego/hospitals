import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { apiErrorMessage } from '@/utils/api-error';
import { HeartPulse, ArrowRight } from 'lucide-react';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);

  // El rol lo resuelve el servidor a partir del usuario: no se elige al entrar.
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSigningIn(true);
    try {
      await login(email.trim(), password);
      navigate('/dashboard');
    } catch (loginError) {
      setError(apiErrorMessage(loginError, 'No se pudo iniciar sesion.'));
    } finally {
      setSigningIn(false);
    }
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
          <p className="mb-8 text-slate-500">
            Ingresa con tu usuario: los permisos salen de tu perfil.
          </p>

          {/* Login form */}
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">
                Correo electronico
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="usuario@hospital.local"
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
                required
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={signingIn || !email || !password}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-3 font-semibold text-white shadow-lg shadow-cyan-900/20 transition-all duration-200 hover:shadow-xl hover:shadow-cyan-900/30 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {signingIn ? 'Ingresando...' : 'Acceder'}
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-slate-400">
            Si no tenes usuario, pedile uno a la administracion del sistema.
          </p>
        </div>
      </div>
    </div>
  );
}
