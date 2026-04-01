import { projectColor } from '@/lib/utils';

interface ProjectStat {
  project_name: string;
  project_id: number;
  count: number;
  categories: string;
}

interface KnowledgeStats {
  stats: ProjectStat[];
  total_entries: number;
  total_projects: number;
}

interface Props {
  stats: KnowledgeStats | null;
}

const getCategoryColor = (category: string) => {
  const colors: Record<string, string> = {
    fact: '#3B82F6',
    decision: '#8B5CF6',
    metric: '#10B981',
    issue: '#EF4444',
    insight: '#F59E0B',
    context: '#F59E0B',
    pattern: '#EC4899',
    status: '#6B7280',
    project_context: '#6B7280',
    compliance: '#8B5CF6',
    relationship: '#EC4899',
    risk: '#EF4444',
    contact: '#10B981',
    timeline: '#F59E0B',
  };
  return colors[category.toLowerCase()] || '#6B7280';
};

export function KnowledgeStats({ stats }: Props) {
  if (!stats || !stats.stats) {
    return (
      <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
        <div className="h-40 flex items-center justify-center">
          <div className="animate-pulse text-[#71717A]">Loading stats...</div>
        </div>
      </div>
    );
  }

  const maxCount = Math.max(...stats.stats.map(p => p.count), 1);

  // Aggregate categories from all projects
  const categoryMap = new Map<string, number>();
  stats.stats.forEach(project => {
    if (project.categories) {
      project.categories.split(',').forEach(cat => {
        const trimmedCat = cat.trim();
        categoryMap.set(trimmedCat, (categoryMap.get(trimmedCat) || 0) + 1);
      });
    }
  });

  const categoriesArray = Array.from(categoryMap.entries())
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count);

  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6 space-y-6">
      {/* Header */}
      <h3 className="text-lg font-semibold flex items-center gap-2">
        <span>📊</span> Stats
      </h3>

      {/* Total count */}
      <div className="text-center py-4 bg-[#0A0A0F] rounded-lg">
        <div className="text-3xl font-bold text-[#FAFAFA]">{stats.total_entries}</div>
        <div className="text-xs text-[#71717A] mt-1">Total Entries</div>
      </div>

      {/* Per-project bars */}
      {stats.stats.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-[#71717A] mb-3">By Project</div>
          <div className="space-y-3">
            {stats.stats.map(project => (
              <div key={project.project_id}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[#FAFAFA] truncate">{project.project_name}</span>
                  <span className="text-[#71717A] ml-2 flex-shrink-0">{project.count}</span>
                </div>
                <div className="h-2 bg-[#1A1A1E] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${(project.count / maxCount) * 100}%`,
                      backgroundColor: projectColor(project.project_name)
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Category counts */}
      {categoriesArray.length > 0 && (
        <div className="pt-4 border-t border-[#27272A]">
          <div className="text-xs font-semibold text-[#71717A] mb-3">By Category</div>
          <div className="space-y-2">
            {categoriesArray.map(cat => (
              <div key={cat.category} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: getCategoryColor(cat.category) }}
                  />
                  <span className="text-sm text-[#FAFAFA] capitalize">{cat.category.replace('_', ' ')}</span>
                </div>
                <span className="text-sm text-[#71717A]">{cat.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
