import { Route, Routes } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import HomePage from './pages/HomePage';
import ObservationsPage from './pages/ObservationsPage';
import ChatPage from './pages/ChatPage';
import ReportPage from './pages/ReportPage';
import DashboardPage from './pages/DashboardPage';
import FeedbackPage from './pages/FeedbackPage';
import { MissionProvider, useMissionContext } from './context/MissionContext';

function AppContent() {
  useMissionContext();

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="grid min-h-screen grid-cols-[320px_minmax(0,1fr)] gap-6">
        <Sidebar />
        <main className="bg-slate-50 p-8">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/observations" element={<ObservationsPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/report" element={<ReportPage />} />
            <Route path="/feedback" element={<FeedbackPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <MissionProvider>
      <AppContent />
    </MissionProvider>
  );
}

export default App;
