import { Archive, BarChart3, Layers, MessageSquare, MessageCircleMore, User, ChevronDown } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { useMissionContext } from '../context/MissionContext';
import logo from '../assets/pwc-logo.png';

const navItems = [
  { to: '/', label: 'Dashboard', icon: BarChart3 },
  { to: '/observations', label: 'Observations', icon: Layers },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/report', label: 'Report', icon: Archive },
  { to: '/feedback', label: 'Feedback', icon: MessageCircleMore }
];

export default function Sidebar() {
  const { activeMission, missions, setActiveMissionId } = useMissionContext();
  const [showMissionSelector, setShowMissionSelector] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

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
    <aside className="w-80 border-r border-slate-200 bg-white px-6 py-8 flex flex-col justify-between">
      <div>
        <div className="mb-10 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white shadow-sm">
           <img src={logo} alt="PwC logo" className="h-10 w-auto" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900">Audit ITGC Assistant</p>
            <p className="text-xs text-slate-500">Mission workspace</p>
          </div>
        </div>

        <div className="mb-8 relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setShowMissionSelector(!showMissionSelector)}
            className="flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-left hover:border-slate-300"
          >
            <div>
              <p className="text-sm font-semibold text-slate-900">{activeMission?.name ?? 'Select mission'}</p>
              <p className="mt-1 text-xs text-slate-500">Status: {activeMission?.status ?? 'Draft'}</p>
            </div>
            <ChevronDown className="h-5 w-5 text-slate-500" />
          </button>

          {showMissionSelector && (
            <div className="absolute top-full left-0 right-0 mt-2 rounded-2xl border border-slate-200 bg-white shadow-lg z-10">
              {missions.map((mission) => (
                <button
                  key={mission.mission_id}
                  type="button"
                  onClick={() => {
                    setActiveMissionId(mission.mission_id);
                    setShowMissionSelector(false);
                  }}
                  className={`w-full px-4 py-3 text-left text-sm hover:bg-slate-50 first:rounded-t-2xl last:rounded-b-2xl ${
                    activeMission?.mission_id === mission.mission_id ? 'bg-slate-100 font-semibold' : ''
                  }`}
                >
                  <p className="text-slate-900">{mission.name}</p>
                  <p className="text-xs text-slate-500">Status: {mission.status}</p>
                </button>
              ))}
              {missions.length === 0 && (
                <div className="px-4 py-3 text-sm text-slate-500 text-center">
                  No missions available
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
                  `flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition ${
                    isActive ? 'bg-slate-100 text-slate-900' : 'text-slate-600 hover:bg-slate-50'
                  }`
                }
              >
                <Icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-200 text-slate-700">
            <User className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900">Camille Dupont</p>
            <p className="text-xs text-slate-500">PwC Internal Audit</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
