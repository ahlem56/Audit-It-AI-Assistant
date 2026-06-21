import { useEffect, useRef, useState, type AnimationEvent, type ReactNode } from 'react';
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
import logo from './assets/pwc-logo.png';

function FullScreenStatus({ title, subtitle }: { title: string; subtitle: string }) {
  const { text } = useLanguage();

  return (
    <div className="pwc-loading-page min-h-screen px-6">
      <div className="pwc-loading-status" role="status" aria-live="polite">
        <img className="pwc-loading-logo" src="/pwc-logo.png" alt="" aria-hidden="true" />

        <p className="pwc-loading-kicker">{text.fullScreen.secureWorkspace}</p>
        <h1>{title}</h1>
        <p className="pwc-loading-copy">{subtitle}</p>

        <div className="pwc-loading-line" aria-label="Preparing workspace">
          <span />
        </div>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { initialized, loading, authenticated, authEnabled } = useAuthContext();
  const { text } = useLanguage();

  if (!initialized || loading) {
    return <FullScreenStatus title={text.fullScreen.loadingTitle} subtitle={text.fullScreen.loadingSubtitle} />;
  }

  if (authEnabled && !authenticated) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <>{children}</>;
}

function AppShell() {
  const { activeMissionId } = useMissionContext();
  const location = useLocation();
  const [displayedLocation, setDisplayedLocation] = useState(location);
  const [transitionPhase, setTransitionPhase] = useState<'idle' | 'exit' | 'enter'>('idle');
  const [missionTransitionKey, setMissionTransitionKey] = useState(0);
  const [missionTransitionActive, setMissionTransitionActive] = useState(false);
  const previousMissionId = useRef(activeMissionId);

  useEffect(() => {
    if (!activeMissionId || previousMissionId.current === activeMissionId) return;
    previousMissionId.current = activeMissionId;

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    setMissionTransitionKey((current) => current + 1);
    setMissionTransitionActive(false);
    const frame = window.requestAnimationFrame(() => setMissionTransitionActive(true));
    const settleTimer = window.setTimeout(() => setMissionTransitionActive(false), 820);

    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
    };
  }, [activeMissionId]);

  useEffect(() => {
    if (location.pathname === displayedLocation.pathname) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setDisplayedLocation(location);
      setTransitionPhase('idle');
      return;
    }

    setTransitionPhase('exit');
    const swapTimer = window.setTimeout(() => {
      setDisplayedLocation(location);
      setTransitionPhase('enter');
    }, 280);

    return () => window.clearTimeout(swapTimer);
  }, [location, displayedLocation.pathname]);

  const handleTransitionEnd = (event: AnimationEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget && transitionPhase === 'enter') {
      setTransitionPhase('idle');
    }
  };

  return (
    <div className="pwc-shell min-h-screen">
      <div className="grid min-h-screen grid-cols-1 gap-0 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Sidebar />
        <main className="relative min-w-0 p-4 sm:p-6 lg:p-8">
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_right,_rgba(239,91,12,0.08),_transparent_24%),linear-gradient(180deg,rgba(255,255,255,0.14),transparent)]" />
          <div className={`pwc-page-stage is-${transitionPhase} relative z-[1]`} onAnimationEnd={handleTransitionEnd}>
            <div key={displayedLocation.pathname} className={`pwc-page-content ${missionTransitionActive ? 'pwc-mission-page-enter' : ''}`}>
              <Routes location={displayedLocation}>
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
            </div>
            <div className="pwc-route-veil" aria-hidden="true">
              <div className="pwc-route-veil-panel">
                <span className="pwc-route-rail pwc-route-rail-yellow" />
                <span className="pwc-route-rail pwc-route-rail-red" />
                <span className="pwc-route-rail pwc-route-rail-orange" />
                <img src={logo} alt="" />
              </div>
            </div>
            {missionTransitionKey > 0 && (
              <div key={missionTransitionKey} className="pwc-mission-transition" aria-hidden="true">
                <div className="pwc-mission-transition-surface">
                  <span className="pwc-mission-transition-line pwc-mission-transition-yellow" />
                  <span className="pwc-mission-transition-line pwc-mission-transition-red" />
                  <span className="pwc-mission-transition-line pwc-mission-transition-orange" />
                  <div className="pwc-mission-transition-label">
                    <img src={logo} alt="" />
                    <div>
                      <span>Engagement context</span>
                      <strong>Updating mission workspace</strong>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
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
