import type { ActivityEvent } from '../lib/api';

const KIND_STYLES: Record<string, string> = {
  'task.created': 'text-violet-300 border-violet-500/30',
  'mesh.discovery': 'text-cyan-300 border-cyan-500/30',
  'mesh.verification': 'text-sky-300 border-sky-500/30',
  'mesh.escrow': 'text-amber-300 border-amber-500/30',
  'mesh.invoke': 'text-emerald-300 border-emerald-500/30',
  'mesh.settle': 'text-emerald-400 border-emerald-500/40',
  'mesh.error': 'text-rose-300 border-rose-500/30',
  'agent.registered': 'text-slate-300 border-white/10',
  'agent.verified': 'text-cyan-200 border-cyan-500/20',
};

function kindClass(kind: string) {
  return KIND_STYLES[kind] ?? 'text-slate-400 border-white/10';
}

export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  const sorted = [...events].reverse();
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold text-white">Activity stream</h2>
        <span className="text-xs text-slate-500 font-mono">{sorted.length} events</span>
      </div>
      <ul className="max-h-[420px] overflow-y-auto divide-y divide-white/5">
        {sorted.length === 0 && (
          <li className="px-5 py-8 text-sm text-slate-500 text-center">Waiting for mesh events…</li>
        )}
        {sorted.map((ev) => (
          <li key={ev.id} className="px-5 py-3 hover:bg-white/[0.02] transition">
            <div className="flex flex-wrap items-start gap-2 mb-1">
              <span
                className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${kindClass(ev.kind)}`}
              >
                {ev.kind.replace('mesh.', '').replace('agent.', '')}
              </span>
              <time className="text-[10px] text-slate-600 font-mono ml-auto">{ev.timestamp}</time>
            </div>
            <p className="text-sm text-slate-200">{ev.message}</p>
            {ev.task_id && (
              <p className="text-[10px] text-slate-600 font-mono mt-1 truncate">task {ev.task_id}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
