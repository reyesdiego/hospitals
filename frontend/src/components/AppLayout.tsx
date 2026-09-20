import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { ROLE_LABELS } from '@/auth/types';
import { NAV_ITEMS } from '@/config/nav';
import { HeartPulse, LogOut, Menu, X } from 'lucide-react';

export default function AppLayout() {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  if (!user) return null;

  // Cada pantalla se ve si el usuario tiene alguno de sus permisos; sin permisos, es de todos.
  const items = NAV_ITEMS.filter(
    (item) => item.permissions.length === 0 || item.permissions.some(can),
  );

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/50 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed z-40 flex h-full w-72 flex-col bg-slate-900 text-slate-200 transition-transform duration-300 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="flex h-20 items-center gap-3 border-b border-slate-700/50 px-6">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-teal-400 to-cyan-600 shadow-lg shadow-cyan-900/30">
            <HeartPulse className="h-6 w-6 text-white" strokeWidth={2.2} />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">HospitaLink</h1>
            <p className="text-xs text-slate-400">Gestion de hospitalizacion</p>
          </div>
          <button
            className="ml-auto text-slate-400 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-4 py-6">
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-gradient-to-r from-teal-500/20 to-cyan-500/10 text-teal-300 shadow-inner ring-1 ring-teal-500/30'
                      : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-100'
                  }`
                }
              >
                <Icon className="h-5 w-5 shrink-0" strokeWidth={2} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* User card */}
        <div className="border-t border-slate-700/50 p-4">
          <div className="flex items-center gap-3 rounded-lg bg-slate-800/50 p-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-cyan-600 text-sm font-bold text-white">
              {user.full_name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">{user.full_name}</p>
              <p className="truncate text-xs text-slate-400">{ROLE_LABELS[user.role]}</p>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-red-400"
              title="Cerrar sesion"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-16 items-center gap-4 border-b border-slate-200 bg-white px-6 shadow-sm">
          <button
            className="text-slate-600 lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-6 w-6" />
          </button>
          <div className="flex items-center gap-2 lg:hidden">
            <HeartPulse className="h-5 w-5 text-teal-600" />
            <span className="font-bold text-slate-800">HospitaLink</span>
          </div>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-700">{user.full_name}</p>
              <p className="text-xs text-slate-400">{user.email}</p>
            </div>
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-cyan-600 text-sm font-bold text-white shadow-md"
              >
                {user.full_name.charAt(0).toUpperCase()}
              </button>
              {userMenuOpen && (
                <div
                  className="absolute right-0 top-12 z-50 w-48 rounded-lg border border-slate-200 bg-white py-2 shadow-xl"
                  onMouseLeave={() => setUserMenuOpen(false)}
                >
                  <div className="border-b border-slate-100 px-4 py-2">
                    <p className="text-sm font-semibold text-slate-700">{user.full_name}</p>
                    <p className="text-xs text-slate-400">{ROLE_LABELS[user.role]}</p>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="flex w-full items-center gap-2 px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                  >
                    <LogOut className="h-4 w-4" />
                    Cerrar sesion
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-slate-50 p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
