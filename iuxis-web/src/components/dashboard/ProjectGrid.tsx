'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { PriorityBadge } from '@/components/shared/PriorityBadge';
import { StatusDot } from '@/components/shared/StatusDot';
import type { Project } from '@/lib/types';

type WorkPill = {
  label: string;
  color: string;
  bg: string;
};

interface ProjectGridProps {
  projects: Project[];
}

export function ProjectGrid({ projects }: ProjectGridProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [pillsMap, setPillsMap] = useState<Record<number, WorkPill[]>>({});
  const [pillsLoading, setPillsLoading] = useState(true);

  useEffect(() => {
    async function fetchPills() {
      try {
        const res = await fetch('http://localhost:8000/api/project-pills');
        if (res.ok) {
          const data = await res.json();
          setPillsMap(data.pills || {});
        }
      } catch (e) {
        // silently fail — cards render without pills
      } finally {
        setPillsLoading(false);
      }
    }
    fetchPills();
  }, []);

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <span>📁</span> Projects
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects.map((project) => {
          const isExpanded = expandedId === project.id;
          const hasSubProjects = project.sub_projects && project.sub_projects.length > 0;
          const workPills = pillsMap[project.id] || [];

          return (
            <motion.div
              key={project.id}
              layout
              className="border border-[#27272A] bg-[#09090B] rounded-lg p-4 hover:border-[#3F3F46] transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <StatusDot
                    status={project.status}
                    priority={project.priority}
                    pulse={project.status === 'active'}
                  />
                  <h3 className="font-semibold text-[#FAFAFA]">{project.name}</h3>
                </div>
                <PriorityBadge priority={project.priority} />
              </div>

              <div className="flex items-center gap-2 mb-3 flex-wrap min-h-[22px]">
                {pillsLoading ? (
                  <>
                    <span className="h-[22px] w-20 rounded bg-[#1A1A1E] animate-pulse" />
                    <span className="h-[22px] w-24 rounded bg-[#1A1A1E] animate-pulse" />
                    <span className="h-[22px] w-16 rounded bg-[#1A1A1E] animate-pulse" />
                  </>
                ) : (
                  workPills.map((pill) => (
                  <span
                    key={pill.label}
                    className="text-xs px-2 py-0.5 rounded shrink-0 font-medium"
                    style={{ color: pill.color, backgroundColor: pill.bg }}
                  >
                    {pill.label}
                  </span>
                  ))
                )}
              </div>

              {project.current_focus && (
                <p className="text-sm text-[#A1A1AA] mb-3 line-clamp-2">
                  {project.current_focus}
                </p>
              )}

              <div className="flex items-center gap-3 text-xs text-[#71717A] mb-3">
                {hasSubProjects && (
                  <span className="px-2 py-0.5 rounded-full bg-[#1A1A1E]">
                    {project.sub_projects!.length} sub-projects
                  </span>
                )}
                {project.knowledge_count !== undefined && project.knowledge_count > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-[#1A1A1E]">
                    {project.knowledge_count} knowledge
                  </span>
                )}
              </div>

              {hasSubProjects && (
                <>
                  <button
                    onClick={() => toggleExpand(project.id)}
                    className="flex items-center gap-1 text-xs text-[#3B82F6] hover:text-[#2563EB] font-medium transition-colors"
                  >
                    {isExpanded ? (
                      <>
                        <ChevronUp size={14} /> Hide sub-projects
                      </>
                    ) : (
                      <>
                        <ChevronDown size={14} /> Show sub-projects
                      </>
                    )}
                  </button>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden mt-3 pt-3 border-t border-[#27272A]"
                      >
                        <div className="space-y-2">
                          {project.sub_projects!.map((subProject) => (
                            <div
                              key={subProject.id}
                              className="flex items-center gap-2 p-2 rounded bg-[#1A1A1E] hover:bg-[#27272A] transition-colors"
                            >
                              <StatusDot status={subProject.status} priority={subProject.priority} />
                              <span className="text-sm text-[#FAFAFA] flex-1">
                                {subProject.name}
                              </span>
                              <PriorityBadge priority={subProject.priority} />
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
