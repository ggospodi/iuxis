import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function priorityColor(priority: number): string {
  const colors: Record<number, string> = {
    1: '#EF4444', 2: '#F59E0B', 3: '#3B82F6', 4: '#6B7280', 5: '#4B5563'
  };
  return colors[priority] || '#6B7280';
}

export function priorityLabel(priority: number): string {
  return `P${priority}`;
}

export function severityColor(severity: string): string {
  const colors: Record<string, string> = {
    critical: '#EF4444', warning: '#F59E0B', info: '#3B82F6'
  };
  return colors[severity] || '#6B7280';
}

export function statusColor(status: string): string {
  const colors: Record<string, string> = {
    active: '#10B981', planned: '#3B82F6', paused: '#F59E0B',
    done: '#6B7280', todo: '#A1A1AA', in_progress: '#3B82F6'
  };
  return colors[status] || '#6B7280';
}

export function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return date.toLocaleDateString();
}

// Consistent project colors (deterministic from name)
export function projectColor(name: string): string {
  const colors = ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#06B6D4', '#EC4899', '#14B8A6'];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}
