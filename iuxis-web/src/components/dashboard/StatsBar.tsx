import { FolderKanban, CheckSquare, Brain, Lightbulb } from 'lucide-react';
import type { SystemStats } from '@/lib/types';

interface StatsBarProps {
  stats: SystemStats;
}

export function StatsBar({ stats }: StatsBarProps) {
  const statItems = [
    {
      icon: FolderKanban,
      label: 'Active Projects',
      value: stats.projects.active,
      total: stats.projects.total,
    },
    {
      icon: CheckSquare,
      label: 'Open Tasks',
      value: stats.tasks.todo + stats.tasks.in_progress,
      total: stats.tasks.total,
    },
    {
      icon: Brain,
      label: 'Knowledge Entries',
      value: stats.knowledge.total,
    },
    {
      icon: Lightbulb,
      label: 'New Insights',
      value: stats.insights.new,
      total: stats.insights.total,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {statItems.map((item) => (
        <div
          key={item.label}
          className="bg-[#111113] border border-[#27272A] rounded-xl p-4 hover:border-[#3F3F46] transition-colors"
        >
          <item.icon className="text-[#A1A1AA] mb-3" size={18} />
          <div className="text-4xl font-bold tracking-tight text-[#FAFAFA] leading-none">
            {item.value}
            {item.total !== undefined && (
              <span className="text-base font-normal text-[#52525B] ml-1.5">
                / {item.total}
              </span>
            )}
          </div>
          <div className="text-xs text-[#71717A] mt-2">{item.label}</div>
        </div>
      ))}
    </div>
  );
}
