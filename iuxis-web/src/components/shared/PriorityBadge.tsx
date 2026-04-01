import { priorityColor, priorityLabel } from '@/lib/utils';

interface PriorityBadgeProps {
  priority: number;
}

export function PriorityBadge({ priority }: PriorityBadgeProps) {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold text-white"
      style={{ backgroundColor: priorityColor(priority) }}
    >
      {priorityLabel(priority)}
    </span>
  );
}
