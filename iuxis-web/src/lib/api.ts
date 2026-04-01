import type { Project, Task, KnowledgeEntry, Insight, ScheduleBlock, SystemStats, KnowledgeGraphData } from './types';

const API_BASE = 'http://localhost:8000/api';

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  // Projects
  getProjects: () => fetchAPI<{ projects: Project[]; total: number }>('/projects'),
  getProject: (id: number) => fetchAPI<Project>(`/projects/${id}`),

  // Tasks
  getTasks: (params?: Record<string, string>) => {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI<{ tasks: Task[]; total: number }>(`/tasks${query}`);
  },
  getTodaysTasks: () => fetchAPI<{ tasks: Task[]; total: number }>('/tasks/today'),

  // Knowledge
  getKnowledge: (params?: Record<string, string>) => {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI<{ entries: KnowledgeEntry[]; total: number }>(`/knowledge${query}`);
  },
  searchKnowledge: (q: string) =>
    fetchAPI<{ results: KnowledgeEntry[]; total: number }>(`/knowledge/search?q=${encodeURIComponent(q)}`),
  getKnowledgeStats: () => fetchAPI<any>('/knowledge/stats'),
  getKnowledgeGraph: (params?: Record<string, string>) => {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI<KnowledgeGraphData>(`/knowledge/graph${query}`);
  },
  getUnassignedKnowledge: () => fetchAPI<{ entries: KnowledgeEntry[]; total: number }>('/knowledge/unassigned'),
  assignKnowledge: (entryId: number, projectId: number) =>
    fetchAPI<{ status: string; entry_id: number; project_id: number }>(`/knowledge/${entryId}/assign`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId }),
    }),

  // Intelligence
  getLatestBriefing: () => fetchAPI<{ briefing: string | null; exists: boolean }>('/intelligence/briefing/latest'),
  generateBriefing: () => fetchAPI<any>('/intelligence/briefing/generate', { method: 'POST' }),
  getTodaysSchedule: () => fetchAPI<{ blocks: ScheduleBlock[]; total: number }>('/intelligence/schedule/today'),
  generateSchedule: () => fetchAPI<any>('/intelligence/schedule/generate', { method: 'POST' }),
  getInsights: (params?: Record<string, string>) => {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI<{ insights: Insight[]; total: number }>(`/intelligence/insights${query}`);
  },

  // Chat
  sendMessage: (message: string, channelId: number = 1) =>
    fetchAPI<{ response: string }>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, channel_id: channelId }),
    }),
  getChatHistory: (channelId: number) =>
    fetchAPI<{ messages: any[] }>(`/chat/history/${channelId}`),
  getChannels: () => fetchAPI<{ channels: any[] }>('/chat/channels'),

  // System
  getStats: () => fetchAPI<SystemStats>('/stats'),
  getHealth: () => fetchAPI<{ status: string }>('/health'),
  openInbox: () => fetchAPI<{ status: string; path?: string; error?: string }>('/system/open-inbox'),

  // Settings
  getSettings: () => fetchAPI<Record<string, string>>('/settings'),
  updateSettings: (settings: Record<string, any>) =>
    fetchAPI<{ saved: boolean; count: number }>('/settings', {
      method: 'POST',
      body: JSON.stringify({ settings }),
    }),
};
