export type MeshStats = {
  agents_total: number;
  agents_verified: number;
  tasks_24h: number;
  mesh_hops_24h: number;
  success_rate_24h: number;
  volume_usd_24h: number;
};

export type Agent = {
  id: string;
  name: string;
  endpoint_url: string;
  status: string;
  trust_score: number;
  capabilities: string[];
  verified_at?: string;
  created_at: string;
};

export type ActivityEvent = {
  id: string;
  kind: string;
  message: string;
  task_id?: string;
  agent_id?: string;
  payload: Record<string, unknown>;
  timestamp: string;
};

export type Task = {
  id: string;
  intent: string;
  budget_usd: number;
  status: string;
  selected_agent_id?: string;
  total_spent_usd: number;
  hops: { phase: string; agent_name: string; success: boolean; price_usd: number; latency_ms: number }[];
  created_at: string;
  completed_at?: string;
  error?: string;
};

const API = import.meta.env.VITE_MESH_API_URL ?? '';
const API_TOKEN = import.meta.env.VITE_MESH_API_TOKEN ?? '';

function authHeaders(): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_TOKEN) h.Authorization = `Bearer ${API_TOKEN}`;
  return h;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

export const meshApi = {
  stats: () => get<MeshStats>('/v1/stats'),
  agents: () => get<Agent[]>('/v1/agents?verified_only=true'),
  activity: (limit = 80) => get<ActivityEvent[]>(`/v1/activity?limit=${limit}`),
  tasks: (limit = 12) => get<Task[]>(`/v1/tasks?limit=${limit}`),
  createTask: async (intent: string, budget_usd: number) => {
    const r = await fetch(`${API}/v1/tasks`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ intent, budget_usd, preferred_capabilities: [] }),
    });
    if (!r.ok) throw new Error(`create task ${r.status}`);
    return r.json() as Promise<Task>;
  },
  activityStreamUrl: () => `${API}/v1/activity/stream`,
};
