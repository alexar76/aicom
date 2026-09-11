/** Agent fleet display labels/colors for Live Monitor. */

export const MONITOR_AGENT_DISPLAY: Record<string, { label: string; color: string }> = {
  analyst: { label: 'Analyst', color: '#38bdf8' },
  pm: { label: 'PM', color: '#60a5fa' },
  architect: { label: 'Architect', color: '#a78bfa' },
  designer: { label: 'Designer', color: '#d946ef' },
  developer: { label: 'Developer', color: '#34d399' },
  devops: { label: 'DevOps', color: '#f472b6' },
  qa: { label: 'QA', color: '#fbbf24' },
  security: { label: 'Security', color: '#ef4444' },
  marketing: { label: 'Marketing', color: '#2dd4bf' },
  sales: { label: 'Sales', color: '#fb923c' },
  evolution_analyst: { label: 'Evolution', color: '#818cf8' },
  methodologist: { label: 'Methodologist', color: '#0ea5e9' },
};

export function getMonitorAgentDisplay(type: string) {
  return MONITOR_AGENT_DISPLAY[type] || { label: type, color: '#9ca3af' };
}

export function formatMonitorRelativeTime(ts: number | null | undefined) {
  if (!ts) return '—';
  const secs = Math.floor((Date.now() - ts * 1000) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}
