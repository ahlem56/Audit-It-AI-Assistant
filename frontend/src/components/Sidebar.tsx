import {
  ChevronDown,
  UserRound
} from 'lucide-react';
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
  const roleLabel = user?.role
    ? user.role.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
    : text.sidebar.workspaceMember;
  const navGroups = [
    {
      label: 'Workspace',
      items: [
        { to: '/dashboard', label: text.sidebar.dashboard },
        { to: '/', label: text.sidebar.missionDashboard, end: true },
        { to: '/observations', label: text.sidebar.observations }
      ]
    },
    {
      label: 'Execution',
      items: [
        { to: '/chat', label: text.sidebar.chat },
        { to: '/report', label: text.sidebar.report },
        { to: '/feedback', label: text.sidebar.feedback }
      ]
    },
    {
      label: 'Administration',
      items: [
        { to: '/settings', label: text.sidebar.settings },
        { to: '/notifications', label: 'Notifications' },
        { to: '/security', label: 'Security' }
      ]
    }
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
    <aside className="pwc-sidebar sticky top-0 z-[60] flex w-full flex-col border-b border-slate-200/80 px-4 py-4 lg:h-screen lg:min-h-0 lg:w-[18.5rem] lg:overflow-y-auto lg:border-b-0 lg:border-r lg:px-6 lg:py-7">
      <div>
        <div className="pwc-sidebar-band mb-5 flex items-center gap-2.5 lg:mb-8">
          <div className="flex min-w-0 items-center gap-2.5">
            <img src={logo} alt="PwC logo" className="pwc-sidebar-logo h-12 w-auto shrink-0" />
            <div className="pwc-sidebar-product-wrap relative z-[1] min-w-0">
              <p className="pwc-sidebar-product">{text.sidebar.productName}</p>
            </div>
          </div>
        </div>

        <div className="relative mb-5 lg:mb-8" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setShowMissionSelector(!showMissionSelector)}
            className="pwc-mission-select flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-left transition hover:border-slate-300 lg:py-3.5"
          >
            <div className="min-w-0">
              <p className="pwc-mission-select-name truncate">{activeMission?.name ?? text.sidebar.selectMission}</p>
              <p className="pwc-mission-select-status">
                <span />
                {activeMission?.status ?? 'Draft'}
              </p>
            </div>
            <span className="pwc-mission-select-chevron">
              <ChevronDown className="h-4 w-4" />
            </span>
          </button>

          {showMissionSelector && (
            <div className="pwc-mission-menu absolute left-0 right-0 top-full z-10 mt-2 overflow-hidden border bg-white">
              {missions.map((mission) => (
                <button
                  key={mission.mission_id}
                  type="button"
                  onClick={() => {
                    setActiveMissionId(mission.mission_id);
                    setShowMissionSelector(false);
                  }}
                  className={`pwc-mission-menu-option w-full px-4 py-3 text-left text-sm ${
                    activeMission?.mission_id === mission.mission_id ? 'pwc-mission-menu-option-active font-semibold' : ''
                  }`}
                >
                  <p className="truncate text-slate-900" title={mission.name}>{mission.name}</p>
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

        <nav className="pwc-sidebar-nav -mx-1 flex gap-2 overflow-x-auto px-1 pb-1 lg:mx-0 lg:block lg:space-y-6 lg:overflow-visible lg:px-0 lg:pb-0">
          {navGroups.map((group) => (
            <div key={group.label} className="pwc-sidebar-group">
              <p className="pwc-sidebar-section hidden lg:block">{group.label}</p>
              <div className="lg:space-y-1">
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `pwc-nav-link ${isActive ? 'pwc-nav-link-active' : ''}`
                    }
                  >
                    <span className="whitespace-nowrap">{item.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="pwc-sidebar-account mt-8 hidden lg:block">
          <div className="pwc-sidebar-account-card">
            <NavLink
              to="/settings"
              className="pwc-sidebar-account-link"
              aria-label="Open profile settings"
            >
              {user?.profile_image_url ? (
                <img
                  src={user.profile_image_url}
                  alt={`${user.display_name || user.email || 'User'} profile`}
                  className="pwc-sidebar-avatar object-cover"
                />
              ) : (
                <div className="pwc-sidebar-avatar flex items-center justify-center">
                  <UserRound className="h-5 w-5" />
                </div>
              )}
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-950">{user?.display_name || user?.email || text.sidebar.authenticatedUser}</p>
                <p className="pwc-sidebar-role">{roleLabel}</p>
              </div>
            </NavLink>
            <button
              type="button"
              onClick={() => void logout()}
              className="pwc-sidebar-signout"
            >
              {text.sidebar.signOut}
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
