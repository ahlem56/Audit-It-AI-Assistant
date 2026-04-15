import type { MissionStatus } from '../types';

const badgeStyles: Record<MissionStatus, string> = {
  Draft: 'bg-slate-100 text-slate-700',
  Ready: 'bg-sky-100 text-sky-800',
  Finalized: 'bg-emerald-100 text-emerald-800'
};

interface StatusBadgeProps {
  status: MissionStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${badgeStyles[status]}`}>
      {status}
    </span>
  );
}
