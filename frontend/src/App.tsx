import { type ReactNode } from 'react';
import type { Permission } from '@/api/model';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/auth/AuthContext';
import AppLayout from '@/components/AppLayout';
import LoginPage from '@/pages/LoginPage';
import DashboardPage from '@/pages/DashboardPage';
import PatientsPage from '@/pages/PatientsPage';
import ProfessionalsPage from '@/pages/ProfessionalsPage';
import BedsPage from '@/pages/BedsPage';
import RoomsPage from '@/pages/RoomsPage';
import FacilitiesPage from '@/pages/FacilitiesPage';
import DiagnosesPage from '@/pages/DiagnosesPage';
import MorbidityReportPage from '@/pages/MorbidityReportPage';
import PatientRecordPage from '@/pages/PatientRecordPage';
import ServicesPage from '@/pages/ServicesPage';
import MedicalPracticesPage from '@/pages/MedicalPracticesPage';
import CoveragesPage from '@/pages/CoveragesPage';
import PlanPracticesPage from '@/pages/PlanPracticesPage';
import NursingTasksPage from '@/pages/NursingTasksPage';
import UsersPage from '@/pages/UsersPage';
import HospitalizationsPage from '@/pages/HospitalizationsPage';
import HospitalizationDetailPage from '@/pages/HospitalizationDetailPage';
import AdmissionPanelPage from '@/pages/AdmissionPanelPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** Una pantalla que el usuario no tiene permitida no se muestra vacia: se lo dice. */
function RequirePermission({
  anyOf,
  children,
}: {
  anyOf: Permission[];
  children: ReactNode;
}) {
  const { can } = useAuth();
  if (anyOf.length > 0 && !anyOf.some(can)) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h2 className="text-lg font-bold text-slate-800">No tenes acceso a esta pantalla</h2>
        <p className="mt-2 text-sm text-slate-500">
          Tu usuario no tiene los permisos necesarios. Si deberias tenerlos, pedilo a la
          administracion del sistema.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

const screen = (anyOf: Permission[], element: ReactNode) => (
  <RequirePermission anyOf={anyOf}>{element}</RequirePermission>
);

function AppRoutes() {
  const { user, loading } = useAuth();
  // Mientras se revalida la sesion guardada no se decide nada: evita el salto a /login.
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-teal-500" />
      </div>
    );
  }
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/dashboard" replace />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/patients" element={screen(['ADMISSION'], <PatientsPage />)} />
        <Route
          path="/patients/:id"
          element={screen(['ADMISSION', 'HOSPITALIZATION'], <PatientRecordPage />)}
        />
        <Route path="/professionals" element={screen(['CATALOG'], <ProfessionalsPage />)} />
        <Route path="/admissions" element={screen(['ADMISSION'], <AdmissionPanelPage />)} />
        <Route path="/beds" element={screen(['BED_CLEANING', 'BED_MANAGEMENT'], <BedsPage />)} />
        <Route path="/rooms" element={screen(['CATALOG'], <RoomsPage />)} />
        <Route path="/facilities" element={screen(['CATALOG'], <FacilitiesPage />)} />
        <Route path="/services" element={screen(['CATALOG'], <ServicesPage />)} />
        <Route path="/practices" element={screen(['CATALOG'], <MedicalPracticesPage />)} />
        <Route path="/diagnoses" element={screen(['CATALOG'], <DiagnosesPage />)} />
        <Route
          path="/reports/morbidity"
          element={screen(['HOSPITALIZATION', 'ADMISSION'], <MorbidityReportPage />)}
        />
        <Route path="/coverages" element={screen(['CATALOG'], <CoveragesPage />)} />
        <Route path="/coverages/plans/:planId" element={screen(['CATALOG'], <PlanPracticesPage />)} />
        <Route path="/nursing-tasks" element={screen(['NURSING_TASKS'], <NursingTasksPage />)} />
        <Route path="/users" element={screen(['USER_ADMIN'], <UsersPage />)} />
        <Route path="/hospitalizations" element={screen(['HOSPITALIZATION', 'ADMISSION'], <HospitalizationsPage />)} />
        <Route path="/hospitalizations/:id" element={screen(['HOSPITALIZATION', 'ADMISSION'], <HospitalizationDetailPage />)} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
