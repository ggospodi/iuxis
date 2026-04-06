'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { BriefingCard } from '@/components/dashboard/BriefingCard';
import { StatsBar } from '@/components/dashboard/StatsBar';
import { ProjectGrid } from '@/components/dashboard/ProjectGrid';
import { InsightsFeed } from '@/components/dashboard/InsightsFeed';
import { KnowledgeRecent } from '@/components/dashboard/KnowledgeRecent';

const safe = <T,>(promise: Promise<T>, fallback: T): Promise<T> =>
  promise.catch(() => fallback);

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDashboard() {
      const [stats, projects, briefing, insights, knowledge] = await Promise.all([
        safe(api.getStats(), {}),
        safe(api.getProjects(), { projects: [] }),
        safe(api.getLatestBriefing(), null),
        safe(api.getInsights({ limit: '20' }), { insights: [] }),
        safe(api.getKnowledge({ limit: '15' }), { entries: [] }),
      ]);
      setData({ stats, projects, briefing, insights, knowledge });
      setLoading(false);
    }
    loadDashboard();
  }, []);

  if (loading) return <DashboardSkeleton />;

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      <StatsBar stats={data.stats} />

      {/* Today's Focus — full width (renamed briefing) */}
      <BriefingCard briefing={data.briefing} title="Today's Focus" projectCount={data.projects.projects?.length ?? 0} />

      {/* Project Cards — full width */}
      <ProjectGrid projects={data.projects.projects} />

      {/* Insights + Recent Knowledge — 50/50 */}
      <div className="grid grid-cols-2 gap-6">
        <InsightsFeed insights={data.insights.insights} />
        <KnowledgeRecent entries={data.knowledge.entries} />
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="p-6 space-y-6 animate-pulse max-w-[1400px] mx-auto">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 bg-[#111113] rounded-xl" />
        ))}
      </div>
      <div className="h-40 bg-[#111113] rounded-xl" />
      <div className="h-96 bg-[#111113] rounded-xl" />
      <div className="grid grid-cols-2 gap-6">
        <div className="h-64 bg-[#111113] rounded-xl" />
        <div className="h-64 bg-[#111113] rounded-xl" />
      </div>
    </div>
  );
}
