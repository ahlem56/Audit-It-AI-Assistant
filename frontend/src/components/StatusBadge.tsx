import type { MissionStatus } from '../types';

const badgeStyles: Record<MissionStatus, string> = {
  Draft: 'bg-slate-100 text-slate-700',
  Ready: 'bg-[#fff1e8] text-[#ef5b0c]',
  Finalized: 'bg-[#fde7e3] text-[#c74634]'
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
