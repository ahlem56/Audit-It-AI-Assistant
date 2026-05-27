import { Archive, BarChart3, BellRing, Layers, MessageSquare, MessageCircleMore, ShieldCheck, User, ChevronDown, Settings } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { useMissionContext } from '../context/MissionContext';
import { useAuthContext } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import logo from '../assets/pwc-logo.png';

export default function Sidebar() {
  const { activeMission, missions, setActiveMissionId } = useMissionContext();
  const { user, logout } = useAuthContext();
  const { text } = useLanguage();
  const [showMissionSelector, setShowMissionSelector] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navItems = [
    { to: '/', label: text.sidebar.dashboard, icon: BarChart3 },
    { to: '/observations', label: text.sidebar.observations, icon: Layers },
    { to: '/chat', label: text.sidebar.chat, icon: MessageSquare },
    { to: '/report', label: text.sidebar.report, icon: Archive },
    { to: '/feedback', label: text.sidebar.feedback, icon: MessageCircleMore },
    { to: '/settings', label: text.sidebar.settings, icon: Settings },
    { to: '/notifications', label: 'Notifications', icon: BellRing },
    { to: '/security', label: 'Security', icon: ShieldCheck }
  ];

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowMissionSelector(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <aside className="pwc-sidebar relative flex w-80 flex-col border-r border-slate-200/80 px-6 py-8">
      <div className="pointer-events-none absolute inset-y-0 right-0 w-px bg-white/70" />
      <div>
        <div className="pwc-sidebar-band mb-10 flex items-center gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="pwc-logo-shell flex h-25 w-16 items-center justify-center rounded-2xl">
              <img src={logo} alt="PwC logo" className="h-10 w-auto" />
            </div>
            <div className="relative z-[1] min-w-0">
              <p className="truncate text-sm font-semibold text-slate-950">{text.sidebar.productName}</p>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-700">{text.sidebar.workspace}</p>
            </div>
          </div>
        </div>

        <div className="mb-8 relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setShowMissionSelector(!showMissionSelector)}
            className="flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-white/80 px-4 py-4 text-left hover:border-slate-300 hover:bg-white"
          >
            <div>
              <p className="text-sm font-semibold text-slate-900">{activeMission?.name ?? text.sidebar.selectMission}</p>
              <p className="mt-1 text-xs text-slate-500">{text.sidebar.status}: {activeMission?.status ?? 'Draft'}</p>
            </div>
            <ChevronDown className="h-5 w-5 text-slate-500" />
          </button>

          {showMissionSelector && (
            <div className="absolute left-0 right-0 top-full z-10 mt-2 rounded-2xl border border-slate-200 bg-white shadow-lg">
              {missions.map((mission) => (
                <button
                  key={mission.mission_id}
                  type="button"
                  onClick={() => {
                    setActiveMissionId(mission.mission_id);
                    setShowMissionSelector(false);
                  }}
                  className={`w-full px-4 py-3 text-left text-sm first:rounded-t-2xl last:rounded-b-2xl ${
                    activeMission?.mission_id === mission.mission_id ? 'bg-[#fff3eb] font-semibold' : 'hover:bg-slate-50'
                  }`}
                >
                  <p className="text-slate-900">{mission.name}</p>
                  <p className="text-xs text-slate-500">{text.sidebar.status}: {mission.status}</p>
                </button>
              ))}
              {missions.length === 0 && (
                <div className="px-4 py-3 text-center text-sm text-slate-500">
                  {text.sidebar.noMissions}
                </div>
              )}
            </div>
          )}
        </div>

        <nav className="space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `pwc-nav-link ${isActive ? 'pwc-nav-link-active' : ''}`
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon className={`h-5 w-5 ${isActive ? 'text-[#ff8b42]' : ''}`} />
                    {item.label}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
        <div className="mt-8 rounded-3xl border border-slate-200 bg-white/75 p-4 backdrop-blur">
          <NavLink
            to="/settings"
            className="flex items-center gap-3 rounded-2xl p-1 transition hover:bg-slate-50 focus:outline-none"
            aria-label="Open profile settings"
          >
            {user?.profile_image_url ? (
              <img
                src={user.profile_image_url}
                alt={`${user.display_name || user.email || 'User'} profile`}
                className="h-10 w-10 rounded-2xl object-cover ring-1 ring-slate-200"
              />
            ) : (
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                <User className="h-5 w-5" />
              </div>
            )}
            <div>
              <p className="text-sm font-semibold text-slate-900">{user?.display_name || user?.email || text.sidebar.authenticatedUser}</p>
              <p className="text-xs text-slate-500">{user?.organization || user?.email || text.sidebar.workspaceMember}</p>
            </div>
          </NavLink>
          <button
            type="button"
            onClick={() => void logout()}
            className="mt-4 w-full rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-[#ef5b0c]/40 hover:bg-[#fffaf6]"
          >
            {text.sidebar.signOut}
          </button>
        </div>
      </div>
    </aside>
  );
}
