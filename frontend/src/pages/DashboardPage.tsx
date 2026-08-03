import { useQuery } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { useAuth } from '@/auth/AuthContext';
import { ROLE_LABELS } from '@/auth/types';
import { BedCard } from '@/components/BedCard';
import { PageHeader, StatCard, Card, Spinner, ErrorState } from '@/components/ui';
import { Users, BedDouble, Activity, TrendingUp } from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();
  const api = getDefault();

  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });

  const bedsQuery = useQuery({
    queryKey: ['beds'],
    queryFn: () => api.listBedsApiV1BedsGet(),
  });

  const isLoading = patientsQuery.isLoading || bedsQuery.isLoading;
  const isError = patientsQuery.isError || bedsQuery.isError;

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState message="No se pudieron cargar los datos del panel." />;

  const patients = patientsQuery.data ?? [];
  const beds = bedsQuery.data ?? [];

  const availableBeds = beds.filter((b) => b.status === 'AVAILABLE').length;
  const occupiedBeds = beds.filter((b) => b.status === 'OCCUPIED').length;
  const totalBeds = beds.length;
  const occupancyRate = totalBeds > 0 ? Math.round((occupiedBeds / totalBeds) * 100) : 0;

  return (
    <div>
      <PageHeader
        title={`Bienvenido, ${user?.name}`}
        subtitle={`Conectado como ${user ? ROLE_LABELS[user.role] : ''} - Resumen general del sistema`}
      />

      {/* Stats */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Pacientes registrados"
          value={patients.length}
          icon={<Users className="h-6 w-6 text-teal-600" />}
          color="bg-teal-50"
        />
        <StatCard
          label="Camas totales"
          value={totalBeds}
          icon={<BedDouble className="h-6 w-6 text-cyan-600" />}
          color="bg-cyan-50"
        />
        <StatCard
          label="Camas disponibles"
          value={availableBeds}
          icon={<Activity className="h-6 w-6 text-emerald-600" />}
          color="bg-emerald-50"
        />
        <StatCard
          label="Tasa de ocupacion"
          value={`${occupancyRate}%`}
          icon={<TrendingUp className="h-6 w-6 text-amber-600" />}
          color="bg-amber-50"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent patients */}
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-bold text-slate-800">Pacientes recientes</h3>
          <div className="space-y-3">
            {patients.slice(0, 5).map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-3 rounded-lg border border-slate-100 p-3 transition-colors hover:bg-slate-50"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-cyan-600 text-sm font-bold text-white">
                  {p.first_name.charAt(0)}
                  {p.last_name.charAt(0)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-slate-700">
                    {p.first_name} {p.last_name}
                  </p>
                  <p className="truncate text-xs text-slate-400">
                    {p.document_type}: {p.document_number}
                  </p>
                </div>
              </div>
            ))}
            {patients.length === 0 && (
              <p className="py-4 text-center text-sm text-slate-400">No hay pacientes</p>
            )}
          </div>
        </Card>

        {/* Bed overview */}
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-bold text-slate-800">Estado de camas</h3>
          <div className="space-y-3">
            {beds.slice(0, 6).map((b) => (
              <BedCard key={b.id} bed={b} compact showWard />
            ))}
            {beds.length === 0 && (
              <p className="py-4 text-center text-sm text-slate-400">No hay camas</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
