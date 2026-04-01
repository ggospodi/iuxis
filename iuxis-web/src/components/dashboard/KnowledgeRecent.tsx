'use client';

import { useState } from 'react';
import { ProjectBadge } from '@/components/shared/ProjectBadge';
import { TimeAgo } from '@/components/shared/TimeAgo';
import type { KnowledgeEntry } from '@/lib/types';

interface KnowledgeRecentProps {
  entries: KnowledgeEntry[];
}

export function KnowledgeRecent({ entries }: KnowledgeRecentProps) {
  const [selectedProject, setSelectedProject] = useState<string>('all');

  const projects = Array.from(
    new Set(entries.map((e) => e.project_name).filter(Boolean))
  ) as string[];

  const filteredEntries =
    selectedProject === 'all'
      ? entries
      : entries.filter((e) => e.project_name === selectedProject);

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      FACT: '#3B82F6',
      DECISION: '#8B5CF6',
      METRIC: '#10B981',
      ISSUE: '#EF4444',
      INSIGHT: '#F59E0B',
    };
    return colors[category.toUpperCase()] || '#6B7280';
  };

  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <span>📚</span> Recent Knowledge
        </h2>

        {projects.length > 0 && (
          <select
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
            className="px-3 py-1.5 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-sm text-[#FAFAFA] focus:outline-none focus:border-[#3B82F6] transition-colors"
          >
            <option value="all">All Projects</option>
            {projects.map((project) => (
              <option key={project} value={project}>
                {project}
              </option>
            ))}
          </select>
        )}
      </div>

      {filteredEntries.length === 0 ? (
        <p className="text-[#71717A] text-sm">No knowledge entries yet.</p>
      ) : (
        <>
          <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
            {filteredEntries.slice(0, 10).map((entry) => (
              <div
                key={entry.id}
                className="p-3 rounded-lg border border-[#27272A] hover:border-[#3F3F46] transition-colors"
              >
                <div className="flex items-start gap-2 mb-2">
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded"
                    style={{
                      backgroundColor: getCategoryColor(entry.category),
                      color: 'white',
                    }}
                  >
                    {entry.category}
                  </span>
                  {entry.confidence && (
                    <span className="text-xs text-[#71717A] capitalize">
                      {entry.confidence}
                    </span>
                  )}
                </div>

                <p className="text-sm text-[#FAFAFA] mb-2 line-clamp-2">
                  {entry.content}
                </p>

                <div className="flex items-center gap-2 flex-wrap text-xs">
                  {entry.project_name && (
                    <ProjectBadge name={entry.project_name} />
                  )}
                  {entry.source_file && (
                    <span className="text-[#71717A] font-mono">
                      {entry.source_file}
                    </span>
                  )}
                  <span className="text-[#71717A]">•</span>
                  <TimeAgo date={entry.created_at} />
                </div>
              </div>
            ))}
          </div>

          {entries.length > 10 && (
            <div className="mt-4 text-center">
              <a
                href="/knowledge"
                className="text-sm text-[#3B82F6] hover:text-[#2563EB] font-medium transition-colors"
              >
                View all →
              </a>
            </div>
          )}
        </>
      )}
    </div>
  );
}
