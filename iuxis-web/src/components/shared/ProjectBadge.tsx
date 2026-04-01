import { projectColor } from '@/lib/utils';

interface ProjectBadgeProps {
  name: string;
}

export function ProjectBadge({ name }: ProjectBadgeProps) {
  const color = projectColor(name);

  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium text-white border-l-2"
      style={{
        borderLeftColor: color,
        backgroundColor: 'rgba(255, 255, 255, 0.05)'
      }}
    >
      {name}
    </span>
  );
}
