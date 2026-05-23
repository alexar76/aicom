import type { MeshStats } from '../lib/api';

const cards: { key: keyof MeshStats; label: string; format?: (v: number) => string }[] = [
  { key: 'agents_verified', label: 'Verified agents' },
  { key: 'tasks_24h', label: 'Tasks (24h)' },
  { key: 'mesh_hops_24h', label: 'Mesh hops (24h)' },
  {
    key: 'success_rate_24h',
    label: 'Success rate',
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'volume_usd_24h',
    label: 'Volume (24h)',
    format: (v) => `$${v.toFixed(2)}`,
  },
];

export function StatsBar({ stats }: { stats: MeshStats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {cards.map(({ key, label, format }) => (
        <div
          key={key}
          className="rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.06] to-transparent p-4"
        >
          <p className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">{label}</p>
          <p className="font-display text-2xl font-bold text-white tabular-nums">
            {format ? format(stats[key] as number) : String(stats[key])}
          </p>
        </div>
      ))}
    </div>
  );
}
