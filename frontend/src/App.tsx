import { useEffect, type ReactNode } from 'react';
import { Route, Routes, Navigate, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import NotificationToaster from './components/NotificationToaster';
import HomePage from './pages/HomePage';
import ObservationsPage from './pages/ObservationsPage';
import ChatPage from './pages/ChatPage';
import ReportPage from './pages/ReportPage';
import DashboardPage from './pages/DashboardPage';
import FeedbackPage from './pages/FeedbackPage';
import LoginPage from './pages/LoginPage';
import SettingsPage from './pages/SettingsPage';
import NotificationsPage from './pages/NotificationsPage';
import SecurityPage from './pages/SecurityPage';
import { MissionProvider, useMissionContext } from './context/MissionContext';
import { AuthProvider, useAuthContext } from './context/AuthContext';
import { LanguageProvider, useLanguage } from './context/LanguageContext';
import { applyThemePreference, readStoredTheme } from './utils/theme';
import { ShieldCheck } from 'lucide-react';

function FullScreenStatus({ title, subtitle }: { title: string; subtitle: string }) {
  const { text } = useLanguage();

  return (
    <div className="pwc-shell flex min-h-screen items-center justify-center px-6">
      <div className="loading-panel loading-panel-simple w-full max-w-xl rounded-[1.75rem] border p-8 shadow-2xl sm:p-10">
        <div className="flex items-start gap-5">
          <div className="loading-mark" aria-hidden="true">
            <div className="loading-mark-core">
              <ShieldCheck className="h-6 w-6 text-white" />
            </div>
          </div>

          <div className="min-w-0 flex-1">
            <p className="pwc-kicker">{text.fullScreen.secureWorkspace}</p>
            <h1 className="pwc-title mt-3 text-3xl font-semibold leading-tight text-slate-950 sm:text-4xl">{title}</h1>
            <p className="mt-4 text-sm leading-6 text-slate-600 sm:text-base">{subtitle}</p>
          </div>
        </div>

        <div className="mt-9">
          <div className="mb-3 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            <span>Initializing</span>
            <span>Secure</span>
          </div>
          <div className="loading-readiness-track loading-readiness-track-simple" aria-label="Preparing workspace">
            <span />
          </div>
        </div>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { initialized, loading, authenticated } = useAuthContext();
  const { text } = useLanguage();

  if (!initialized || loading) {
    return <FullScreenStatus title={text.fullScreen.loadingTitle} subtitle={text.fullScreen.loadingSubtitle} />;
  }

  if (!authenticated) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <>{children}</>;
}

function AppShell() {
  useMissionContext();

  return (
    <div className="pwc-shell min-h-screen">
      <div className="grid min-h-screen grid-cols-[320px_minmax(0,1fr)] gap-0">
        <Sidebar />
        <main className="relative p-6 lg:p-8">
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_right,_rgba(239,91,12,0.08),_transparent_24%),linear-gradient(180deg,rgba(255,255,255,0.14),transparent)]" />
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/observations" element={<ObservationsPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/report" element={<ReportPage />} />
            <Route path="/feedback" element={<FeedbackPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/security" element={<SecurityPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <NotificationToaster />
      </div>
    </div>
  );
}

function ProtectedApp() {
  return (
    <ProtectedRoute>
      <MissionProvider>
        <AppShell />
      </MissionProvider>
    </ProtectedRoute>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<ProtectedApp />} />
    </Routes>
  );
}

function App() {
  useEffect(() => {
    applyThemePreference(readStoredTheme());
  }, []);

  return (
    <AuthProvider>
      <LanguageProvider>
        <AppRoutes />
      </LanguageProvider>
    </AuthProvider>
  );
}

export default App;
