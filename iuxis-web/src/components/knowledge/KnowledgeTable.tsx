import { useState, useMemo } from 'react';
import type { KnowledgeEntry, Project, KnowledgeGraphData } from '@/lib/types';
import { ProjectBadge } from '@/components/shared/ProjectBadge';
import { TimeAgo } from '@/components/shared/TimeAgo';
import { api } from '@/lib/api';

const getCategoryColor = (category: string) => {
  const colors: Record<string, string> = {
    FACT: '#3B82F6',
    DECISION: '#8B5CF6',
    METRIC: '#10B981',
    ISSUE: '#EF4444',
    INSIGHT: '#F59E0B',
    CONTEXT: '#F59E0B',
    COMPLIANCE: '#EC4899',
    TIMELINE: '#F97316',
    PATTERN: '#EC4899',
    RELATIONSHIP: '#06B6D4',
    RISK: '#EF4444',
    STATUS: '#6B7280',
    CONTACT: '#10B981',
    'PROJECT CONTEXT': '#8B5CF6',
  };
  return colors[category.toUpperCase()] || '#6B7280';
};

const RELATIONSHIP_COLORS: Record<string, string> = {
  causes: '#EF4444',
  blocks: '#EF4444',
  enables: '#10B981',
  depends_on: '#3B82F6',
  contradicts: '#F97316',
  supersedes: '#6B7280',
  references: '#6B7280',
  supports: '#14B8A6',
};

interface RelatedEntry {
  entry: KnowledgeEntry;
  relationshipType: string;
  direction: 'outgoing' | 'incoming';
}

function getRelatedEntries(
  entry: KnowledgeEntry,
  allEntries: KnowledgeEntry[],
  graphData: KnowledgeGraphData | null
): RelatedEntry[] {
  if (!graphData) {
    // Fallback to heuristic if no graph data
    const sameProject = allEntries.filter(
      e => e.id !== entry.id && e.project_id === entry.project_id && e.category !== entry.category
    );
    const crossProject = allEntries.filter(
      e => e.id !== entry.id && e.project_id !== entry.project_id && e.category === entry.category
    );
    const candidates = [...sameProject, ...crossProject].slice(0, 3);
    return candidates.map(e => ({ entry: e, relationshipType: 'related', direction: 'outgoing' as const }));
  }

  const related: RelatedEntry[] = [];

  // Find edges where this entry is the source or target
  for (const edge of graphData.edges) {
    if (edge.from_id === entry.id) {
      // Outgoing edge
      const targetEntry = allEntries.find(e => e.id === edge.to_id);
      if (targetEntry) {
        related.push({
          entry: targetEntry,
          relationshipType: edge.relationship_type,
          direction: 'outgoing',
        });
      }
    } else if (edge.to_id === entry.id) {
      // Incoming edge
      const sourceEntry = allEntries.find(e => e.id === edge.from_id);
      if (sourceEntry) {
        related.push({
          entry: sourceEntry,
          relationshipType: edge.relationship_type,
          direction: 'incoming',
        });
      }
    }
  }

  // Return up to 3
  return related.slice(0, 3);
}

interface Props {
  entries: KnowledgeEntry[];
  allEntries: KnowledgeEntry[];
  loading: boolean;
  projects: Project[];
  graphData: KnowledgeGraphData | null;
  onAssignmentChange?: () => void;
}

export function KnowledgeTable({ entries, allEntries, loading, projects, graphData, onAssignmentChange }: Props) {
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [expandedRelatedIds, setExpandedRelatedIds] = useState<Set<number>>(new Set());

  const categories = useMemo(
    () => Array.from(new Set(allEntries.map(e => e.category))).sort(),
    [allEntries]
  );

  const filteredEntries = useMemo(() => {
    return entries.filter(e => {
      const categoryMatch = !selectedCategory || e.category === selectedCategory;
      let projectMatch = true;
      if (selectedProject) {
        if (selectedProject === 'unassigned') {
          projectMatch = e.project_id === null || e.project_id === undefined;
        } else {
          projectMatch = String(e.project_id) === selectedProject;
        }
      }
      return categoryMatch && projectMatch;
    });
  }, [entries, selectedCategory, selectedProject]);

  const toggleExpanded = (id: number) => {
    const newExpanded = new Set(expandedIds);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedIds(newExpanded);
  };

  const toggleRelated = (id: number) => {
    const newExpanded = new Set(expandedRelatedIds);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedRelatedIds(newExpanded);
  };

  if (loading) {
    return (
      <div className="border border-[#27272A] bg-[#111113] rounded-xl p-8">
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-[#1A1A1E] rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (filteredEntries.length === 0) {
    return (
      <div className="border border-[#27272A] bg-[#111113] rounded-xl overflow-hidden">
        <div className="p-4 border-b border-[#27272A] flex gap-3">
          <FilterSelect
            value={selectedCategory}
            onChange={setSelectedCategory}
            placeholder="All Categories"
            options={categories.map(c => ({ value: c, label: c }))}
          />
          <FilterSelect
            value={selectedProject}
            onChange={setSelectedProject}
            placeholder="All Projects"
            options={[
              { value: 'unassigned', label: '🔸 Unassigned' },
              ...projects.map(p => ({ value: String(p.id), label: p.name }))
            ]}
          />
        </div>
        <div className="p-12 text-center">
          <p className="text-[#FAFAFA] mb-2">No knowledge entries found</p>
          <p className="text-sm text-[#71717A]">Try adjusting your filters or ingesting more project files</p>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl overflow-hidden">
      {/* Filters row */}
      <div className="p-4 border-b border-[#27272A] flex gap-3">
        <FilterSelect
          value={selectedCategory}
          onChange={setSelectedCategory}
          placeholder="All Categories"
          options={categories.map(c => ({ value: c, label: c }))}
        />
        <FilterSelect
          value={selectedProject}
          onChange={setSelectedProject}
          placeholder="All Projects"
          options={[
            { value: 'unassigned', label: '🔸 Unassigned' },
            ...projects.map(p => ({ value: String(p.id), label: p.name }))
          ]}
        />
        {(selectedCategory || selectedProject) && (
          <button
            onClick={() => { setSelectedCategory(''); setSelectedProject(''); }}
            className="px-3 py-2 text-xs text-[#71717A] hover:text-[#FAFAFA] border border-[#27272A] rounded-lg transition-colors"
          >
            Clear filters
          </button>
        )}
        <span className="ml-auto flex items-center text-xs text-[#71717A]">
          {filteredEntries.length} entries
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-[#27272A] bg-[#0A0A0F]">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-[#71717A] uppercase w-24">Category</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-[#71717A] uppercase">Content</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-[#71717A] uppercase w-32">Project</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-[#71717A] uppercase w-56">Related</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-[#71717A] uppercase w-20">Date</th>
            </tr>
          </thead>
          <tbody>
            {filteredEntries.map(entry => {
              const related = getRelatedEntries(entry, allEntries, graphData);
              return (
                <tr
                  key={entry.id}
                  className="border-b border-[#27272A] hover:bg-[#1A1A1E] transition-colors"
                >
                  <td className="px-4 py-3 align-top">
                    <span
                      className="inline-block px-2 py-1 rounded text-xs font-semibold text-white whitespace-nowrap"
                      style={{ backgroundColor: getCategoryColor(entry.category) }}
                    >
                      {entry.category}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <p
                      className={`text-sm text-[#FAFAFA] ${expandedIds.has(entry.id) ? '' : 'line-clamp-2'} cursor-pointer`}
                      onClick={() => toggleExpanded(entry.id)}
                    >
                      {entry.content}
                    </p>
                    {entry.confidence && (
                      <div className="text-xs text-[#71717A] mt-1">
                        Confidence: {entry.confidence}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    {entry.project_id ? (
                      <ProjectBadge name={entry.project_name} />
                    ) : (
                      <UnassignedDropdown
                        entryId={entry.id}
                        projects={projects}
                        onAssign={async (projectId) => {
                          try {
                            await api.assignKnowledge(entry.id, projectId);
                            onAssignmentChange?.();
                          } catch (err) {
                            console.error('Failed to assign entry:', err);
                          }
                        }}
                      />
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    {related.length > 0 ? (
                      <div className="space-y-2">
                        {related.map((r, idx) => {
                          const arrow = r.direction === 'outgoing' ? '→' : '←';
                          const relationshipColor = RELATIONSHIP_COLORS[r.relationshipType] || '#6B7280';
                          return (
                            <div
                              key={`${r.entry.id}-${idx}`}
                              className="flex items-start gap-1.5 group cursor-pointer"
                              onClick={() => toggleRelated(r.entry.id)}
                            >
                              <span
                                className="mt-0.5 text-xs font-bold flex-shrink-0 leading-relaxed"
                                style={{ color: relationshipColor }}
                                title={`${arrow} ${r.relationshipType}`}
                              >
                                {arrow}
                              </span>
                              <span className={`text-xs text-[#71717A] group-hover:text-[#A1A1AA] transition-colors leading-relaxed ${expandedRelatedIds.has(r.entry.id) ? '' : 'line-clamp-2'}`}>
                                <span className="font-medium" style={{ color: relationshipColor }}>{r.relationshipType}</span>
                                {' · '}
                                {r.entry.content}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-xs text-[#3F3F46]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <TimeAgo date={entry.created_at} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-2 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-sm text-[#FAFAFA] focus:outline-none focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20"
    >
      <option value="">{placeholder}</option>
      {options.map(opt => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
}

function UnassignedDropdown({
  entryId,
  projects,
  onAssign,
}: {
  entryId: number;
  projects: Project[];
  onAssign: (projectId: number) => Promise<void>;
}) {
  const [isAssigning, setIsAssigning] = useState(false);

  const handleAssign = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const projectId = parseInt(e.target.value);
    if (!projectId) return;

    setIsAssigning(true);
    try {
      await onAssign(projectId);
    } finally {
      setIsAssigning(false);
    }
  };

  return (
    <select
      onChange={handleAssign}
      disabled={isAssigning}
      className="px-2 py-1 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-400 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/20 disabled:opacity-50"
    >
      <option value="">Assign to project...</option>
      {projects.map(p => (
        <option key={p.id} value={p.id}>{p.name}</option>
      ))}
    </select>
  );
}
