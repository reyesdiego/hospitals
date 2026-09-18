import { type ReactNode } from 'react';
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
import ServicesPage from '@/pages/ServicesPage';
import MedicalPracticesPage from '@/pages/MedicalPracticesPage';
import HospitalizationsPage from '@/pages/HospitalizationsPage';
import HospitalizationDetailPage from '@/pages/HospitalizationDetailPage';
import AdmissionPanelPage from '@/pages/AdmissionPanelPage';
import { initMockAdapter } from '@/api/mock-adapter';

// The adapter has to replace axios before the first query runs, so it is installed at
// module load instead of inside an effect.
if (import.meta.env.VITE_USE_MOCK_API === 'true') {
  initMockAdapter();
}

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

function AppRoutes() {
  const { user } = useAuth();
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
        <Route path="/patients" element={<PatientsPage />} />
        <Route path="/professionals" element={<ProfessionalsPage />} />
        <Route path="/admissions" element={<AdmissionPanelPage />} />
        <Route path="/beds" element={<BedsPage />} />
        <Route path="/rooms" element={<RoomsPage />} />
        <Route path="/facilities" element={<FacilitiesPage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/practices" element={<MedicalPracticesPage />} />
        <Route path="/hospitalizations" element={<HospitalizationsPage />} />
        <Route path="/hospitalizations/:id" element={<HospitalizationDetailPage />} />
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
