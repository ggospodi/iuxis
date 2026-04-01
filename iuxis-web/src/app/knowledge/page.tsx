'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { KnowledgeEntry, Project, KnowledgeGraphData } from '@/lib/types';
import { KnowledgeSearch } from '@/components/knowledge/KnowledgeSearch';
import { KnowledgeTable } from '@/components/knowledge/KnowledgeTable';
import { KnowledgeStats } from '@/components/knowledge/KnowledgeStats';
import { KnowledgeGraph } from '@/components/knowledge/KnowledgeGraph';
import { Brain } from 'lucide-react';

export default function KnowledgePage() {
  const [allEntries, setAllEntries] = useState<KnowledgeEntry[]>([]);
  const [searchEntries, setSearchEntries] = useState<KnowledgeEntry[] | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null);
  const [unassignedCount, setUnassignedCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'table' | 'graph'>('table');

  const loadData = () => {
    Promise.all([
      api.getKnowledge({ limit: '200' }),
      api.getKnowledgeStats(),
      api.getProjects(),
      api.getKnowledgeGraph(),
      api.getUnassignedKnowledge(),
    ]).then(([knowledge, stats, projects, graph, unassigned]) => {
      setAllEntries(knowledge.entries);
      setStats(stats);
      setProjects(projects.projects);
      setGraphData(graph);
      setUnassignedCount(unassigned.total);
      setLoading(false);
    }).catch(err => {
      console.error('Failed to load knowledge data:', err);
      setLoading(false);
    });
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSearch = async (query: string) => {
    if (!query) {
      setSearchEntries(null);
    } else {
      const data = await api.searchKnowledge(query);
      setSearchEntries(data.results);
    }
  };

  const displayEntries = searchEntries ?? allEntries;

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="w-6 h-6 text-[#8B5CF6]" />
          <h1 className="text-2xl font-bold">Knowledge Base</h1>
          {stats && (
            <span className="text-sm text-[#71717A]">
              {stats.total_entries} entries across {stats.total_projects} projects
            </span>
          )}
          {unassignedCount > 0 && (
            <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
              {unassignedCount} unassigned
            </span>
          )}
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2">
        <button
          onClick={() => setActiveTab('table')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'table'
              ? 'bg-[#1A1A1E] text-[#FAFAFA] border border-[#3B82F6]/20'
              : 'text-[#A1A1AA] hover:text-[#FAFAFA]'
          }`}
        >
          Table
        </button>
        <button
          onClick={() => setActiveTab('graph')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'graph'
              ? 'bg-[#1A1A1E] text-[#FAFAFA] border border-[#3B82F6]/20'
              : 'text-[#A1A1AA] hover:text-[#FAFAFA]'
          }`}
        >
          Graph
        </button>
      </div>

      {/* Search (only show in table view) */}
      {activeTab === 'table' && <KnowledgeSearch onSearch={handleSearch} />}

      {/* Content */}
      {activeTab === 'table' ? (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Main table — 3 columns wide */}
          <div className="lg:col-span-3">
            <KnowledgeTable
              entries={displayEntries}
              allEntries={allEntries}
              loading={loading}
              projects={projects}
              graphData={graphData}
              onAssignmentChange={loadData}
            />
          </div>

          {/* Stats sidebar — 1 column */}
          <div>
            <KnowledgeStats stats={stats} />
          </div>
        </div>
      ) : (
        graphData && <KnowledgeGraph graphData={graphData} projects={projects} />
      )}
    </div>
  );
}
