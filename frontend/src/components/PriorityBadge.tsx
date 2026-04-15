import { Pencil } from 'lucide-react';
import type { PriorityLevel } from '../types';

const priorityStyles: Record<PriorityLevel, string> = {
  Critical: 'bg-red-100 text-red-700',
  High: 'bg-orange-100 text-orange-700',
  Medium: 'bg-amber-100 text-amber-700',
  Low: 'bg-emerald-100 text-emerald-700'
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
        <span className="inline-flex items-center rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-medium text-orange-800">
          <Pencil className="h-3.5 w-3.5" /> overridden
        </span>
      ) : null}
    </div>
  );
}
