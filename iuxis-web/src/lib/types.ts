export interface Project {
  id: number;
  name: string;
  type: string;
  status: string;
  priority: number;
  description: string | null;
  current_focus: string | null;
  time_allocation_hours: number | null;
  parent_id: number | null;
  slug: string | null;
  tags: string | null;
  created_at: string;
  updated_at: string;
  sub_projects?: Project[];
  tasks?: Task[];
  knowledge_count?: number;
}

export interface Task {
  id: number;
  title: string;
  project_id: number;
  project_name?: string;
  priority: number;
  status: string;
  estimated_hours: number | null;
  due_date: string | null;
  tags: string | null;
  created_by: string;
  score?: number;
}

export interface KnowledgeEntry {
  id: number;
  category: string;
  content: string;
  source_file: string | null;
  confidence: string | null;
  tags: string | null;
  status: string;
  created_at: string;
  project_name: string | null;
  project_id: number | null;
}

export interface Insight {
  id: number;
  type: string;
  content: string;
  severity: string;
  status: string;
  created_at: string;
}

export interface ScheduleBlock {
  id: number;
  project_name: string;
  start_time: string;
  end_time: string;
  block_type: string;
  status: string;
  date: string;
}

export interface SystemStats {
  projects: { total: number; top_level: number; active: number };
  tasks: { total: number; todo: number; in_progress: number; done: number };
  knowledge: { total: number };
  insights: { total: number; new: number };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  status?: 'sending' | 'thinking' | 'complete' | 'error';
}

export interface Channel {
  id: number;
  name: string;
  project_id?: number;
  project_name?: string;
}

export interface GraphNode {
  id: number;
  content: string;
  category: string;
  project_id: number | null;
  importance: number | null;
  project_name: string | null;
}

export interface GraphEdge {
  from_id: number;
  to_id: number;
  relationship_type: string;
  confidence: string;
}

export interface KnowledgeGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    total_nodes: number;
    total_edges: number;
    relationship_counts: Record<string, number>;
  };
}
