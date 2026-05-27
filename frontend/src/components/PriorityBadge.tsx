import { Pencil } from 'lucide-react';
import type { PriorityLevel } from '../types';

const priorityStyles: Record<PriorityLevel, string> = {
  Critical: 'bg-[#fde7e3] text-[#c74634]',
  High: 'bg-[#fff1e8] text-[#ef5b0c]',
  Medium: 'bg-[#fff7d9] text-[#b77900]',
  Low: 'bg-[#f3f4f6] text-[#6b7280]'
};

interface PriorityBadgeProps {
  priority: PriorityLevel | null;
  overridden?: boolean;
}

export default function PriorityBadge({ priority, overridden }: PriorityBadgeProps) {
  if (!priority) {
    return (
      <div className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold" aria-label="Not set">
        <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">Not set</span>
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold" aria-label={priority}>
      <span className={priorityStyles[priority]}>{priority}</span>
      {overridden ? (
        <span className="inline-flex items-center rounded-full bg-[#fff1e8] px-2 py-0.5 text-[10px] font-medium text-[#ef5b0c]">
          <Pencil className="h-3.5 w-3.5" /> overridden
        </span>
      ) : null}
    </div>
  );
}
