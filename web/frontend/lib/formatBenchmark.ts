/** Benchmark API returns rates on 0–1 scale; trend_vs_7d is difference in rate units (percentage points when ×100). */

export function formatBenchmarkRate(value: unknown): string {
  if (value === null || value === undefined) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (n >= 0 && n <= 1) return `${Math.round(n * 100)}%`;
  return `${Math.round(n * 100) / 100}`;
}

/** Trend is latest − rolling 7d; display as percentage-point shift. */
export function formatBenchmarkTrend(value: unknown): string {
  if (value === null || value === undefined) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  const pp = n * 100;
  if (Math.abs(pp) < 0.05 && pp !== 0) return `${pp >= 0 ? '+' : ''}${pp.toFixed(2)} pp`;
  const sign = pp > 0 ? '+' : '';
  return `${sign}${pp.toFixed(1)} pp`;
}
