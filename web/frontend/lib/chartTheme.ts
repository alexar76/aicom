/** Shared Recharts styling for admin dark UI. */

export const CHART_COLORS = ['#818cf8', '#34d399', '#fbbf24', '#f472b6', '#22d3ee', '#a78bfa', '#fb923c', '#4ade80'];

export const DARK_CHART_TOOLTIP = {
  contentStyle: {
    background: 'rgba(15, 23, 42, 0.95)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '8px',
    fontSize: '12px',
  },
  labelStyle: { color: '#e2e8f0' },
} as const;

export function usdTooltipFmt(value: number) {
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}
