'use client';

import { useState } from 'react';
import { PriorityBadge } from '@/components/shared/PriorityBadge';
import { ProjectBadge } from '@/components/shared/ProjectBadge';
import { StatusDot } from '@/components/shared/StatusDot';
import type { Task } from '@/lib/types';

interface TodaysFocusProps {
  tasks: Task[];
}

export function TodaysFocus({ tasks }: TodaysFocusProps) {
  const [showAll, setShowAll] = useState(false);
  const displayedTasks = showAll ? tasks : tasks.slice(0, 8);

  const isOverdue = (dueDate: string | null) => {
    if (!dueDate) return false;
    return new Date(dueDate) < new Date();
  };

  const isDueToday = (dueDate: string | null) => {
    if (!dueDate) return false;
    const today = new Date().toDateString();
    return new Date(dueDate).toDateString() === today;
  };

  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <span>🎯</span> Today&apos;s Focus
      </h2>

      {tasks.length === 0 ? (
        <p className="text-[#71717A] text-sm">No tasks scheduled for today.</p>
      ) : (
        <>
          <div className="space-y-3">
            {displayedTasks.map((task) => (
              <div
                key={task.id}
                className="flex items-start gap-3 p-3 rounded-lg hover:bg-[#1A1A1E] transition-colors group"
              >
                <StatusDot
                  status={task.status}
                  pulse={task.status === 'in_progress'}
                />

                <div className="flex-1 min-w-0">
                  <div className="flex items-start gap-2 mb-1">
                    <PriorityBadge priority={task.priority} />
                    <h3 className="text-sm font-medium text-[#FAFAFA] group-hover:text-white flex-1">
                      {task.title}
                    </h3>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    {task.project_name && (
                      <ProjectBadge name={task.project_name} />
                    )}
                    {task.estimated_hours && (
                      <span className="text-xs text-[#71717A]">
                        {task.estimated_hours}h
                      </span>
                    )}
                    {task.due_date && (
                      <span
                        className={`text-xs font-medium ${
                          isOverdue(task.due_date)
                            ? 'text-[#EF4444]'
                            : isDueToday(task.due_date)
                            ? 'text-[#F59E0B]'
                            : 'text-[#71717A]'
                        }`}
                      >
                        {isOverdue(task.due_date)
                          ? 'Overdue'
                          : isDueToday(task.due_date)
                          ? 'Due today'
                          : `Due ${new Date(task.due_date).toLocaleDateString()}`}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {tasks.length > 8 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="mt-4 text-sm text-[#3B82F6] hover:text-[#2563EB] font-medium transition-colors"
            >
              {showAll ? 'Show less' : `Show all (${tasks.length})`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
