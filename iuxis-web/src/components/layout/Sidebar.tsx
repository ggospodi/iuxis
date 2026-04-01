'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import { LayoutDashboard, Brain, Settings, ChevronLeft, ChevronRight } from 'lucide-react';
import { api } from '@/lib/api';
import { projectColor } from '@/lib/utils';

function priorityColor(priority: number): string {
  const colors: Record<number, string> = {
    1: '#EF4444',
    2: '#3B82F6',
    3: '#F59E0B',
    4: '#6B7280',
    5: '#6B7280',
  };
  return colors[priority] || '#6B7280';
}
import type { Project, SystemStats } from '@/lib/types';

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const [projects, setProjects] = useState<Project[]>([]);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [githubStatus, setGithubStatus] = useState<'green' | 'yellow' | 'red' | 'grey'>('grey');

  useEffect(() => {
    async function loadSidebarData() {
      try {
        const [projectsData, statsData] = await Promise.all([
          api.getProjects(),
          api.getStats(),
        ]);
        setProjects(projectsData.projects);
        setStats(statsData);
      } catch (error) {
        console.error('Failed to load sidebar data:', error);
      } finally {
        setLoading(false);
      }
    }
    loadSidebarData();

    // Load GitHub status
    async function loadGithubStatus() {
      try {
        const response = await fetch('http://localhost:8000/api/github/status');
        const data = await response.json();

        if (!data.token_available || data.projects.length === 0) {
          setGithubStatus('grey');
          return;
        }

        // Determine status based on staleness
        const hasVeryStale = data.projects.some((p: any) => p.staleness === 'very_stale');
        const hasStale = data.projects.some((p: any) => p.staleness === 'stale');
        const hasUnscanned = data.projects.some((p: any) => !p.last_scanned);

        if (hasVeryStale || hasUnscanned) {
          setGithubStatus('red');
        } else if (hasStale) {
          setGithubStatus('yellow');
        } else {
          setGithubStatus('green');
        }
      } catch (error) {
        console.error('Failed to load GitHub status:', error);
        setGithubStatus('grey');
      }
    }
    loadGithubStatus();
  }, []);

  const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', href: '/' },
    { icon: Brain, label: 'Knowledge', href: '/knowledge' },
    { icon: Settings, label: 'Settings', href: '/settings' },
  ];

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 64 : 240 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="relative border-r border-[#27272A] bg-[#111113] flex flex-col"
    >
      {/* Header */}
      <div className="p-4 border-b border-[#27272A] flex items-center justify-between">
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="font-bold text-lg"
          >
            Iuxis
          </motion.div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 hover:bg-[#1A1A1E] rounded-lg transition-colors ml-auto"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="p-2 border-b border-[#27272A]">
        {navItems.map((item) => (
          <a
            key={item.label}
            href={item.href}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
              pathname === item.href
                ? 'bg-[#1A1A1E] text-[#FAFAFA] border border-[#3B82F6]/20'
                : 'text-[#A1A1AA] hover:bg-[#1A1A1E] hover:text-[#FAFAFA]'
            }`}
          >
            <item.icon size={20} className="flex-shrink-0" />
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-sm font-medium"
              >
                {item.label}
              </motion.span>
            )}
          </a>
        ))}
      </nav>

      {/* Projects */}
      <div className="flex-1 overflow-y-auto p-2">
        {!collapsed && (
          <div className="text-xs font-semibold text-[#71717A] px-3 py-2 uppercase tracking-wider">
            Projects
          </div>
        )}
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-9 bg-[#1A1A1E] rounded-lg animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="space-y-1">
            {projects.slice(0, 12).map((project) => {
              const color = projectColor(project.name);
              const isPulsing = project.status === 'active';

              return (
                <div
                  key={project.id}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-[#1A1A1E] transition-colors group cursor-pointer"
                >
                  <div className="relative flex-shrink-0">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: priorityColor(project.priority) }}
                    />
                    {isPulsing && (
                      <div
                        className="absolute inset-0 w-2 h-2 rounded-full animate-ping"
                        style={{ backgroundColor: priorityColor(project.priority) }}
                      />
                    )}
                  </div>
                  {!collapsed && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex-1 min-w-0"
                    >
                      <div className="text-sm font-medium text-[#FAFAFA] truncate group-hover:text-white">
                        {project.name}
                      </div>
                      {project.current_focus && (
                        <div className="text-xs text-[#71717A] truncate">
                          {project.current_focus}
                        </div>
                      )}
                    </motion.div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Stats Footer */}
      {stats && (
        <div className="border-t border-[#27272A] p-4">
          {collapsed ? (
            <div className="flex flex-col gap-2 items-center">
              <div className="text-xs font-bold text-[#FAFAFA]">{stats.projects.active}</div>
              <div className="text-xs font-bold text-[#FAFAFA]">{stats.tasks.todo}</div>
              <div className="text-xs font-bold text-[#FAFAFA]">{stats.knowledge.total}</div>
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-2"
            >
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#71717A]">Active Projects</span>
                <span className="text-sm font-semibold text-[#FAFAFA]">{stats.projects.active}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#71717A]">Open Tasks</span>
                <span className="text-sm font-semibold text-[#FAFAFA]">{stats.tasks.todo + stats.tasks.in_progress}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#71717A]">Knowledge</span>
                <span className="text-sm font-semibold text-[#FAFAFA]">{stats.knowledge.total}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#71717A]">GitHub</span>
                <div className="flex items-center gap-1.5">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{
                      backgroundColor:
                        githubStatus === 'green'
                          ? '#10B981'
                          : githubStatus === 'yellow'
                          ? '#F59E0B'
                          : githubStatus === 'red'
                          ? '#EF4444'
                          : '#6B7280',
                    }}
                  />
                  <span className="text-xs font-medium text-[#FAFAFA]">
                    {githubStatus === 'green'
                      ? 'Fresh'
                      : githubStatus === 'yellow'
                      ? 'Stale'
                      : githubStatus === 'red'
                      ? 'Old'
                      : 'Off'}
                  </span>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      )}
    </motion.aside>
  );
}
