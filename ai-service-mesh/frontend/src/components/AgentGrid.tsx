import type { Agent } from '../lib/api';

export function AgentGrid({ agents }: { agents: Agent[] }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <h2 className="font-display text-lg font-semibold text-white mb-4">Verified agents</h2>
      <ul className="space-y-3">
        {agents.map((a) => (
          <li key={a.id} className="rounded-xl border border-white/5 bg-black/30 p-3">
            <div className="flex justify-between items-start gap-2">
              <span className="font-medium text-white text-sm">{a.name}</span>
              <span className="text-xs font-mono text-cyan-300 tabular-nums">
                {(a.trust_score * 100).toFixed(0)}% trust
              </span>
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {a.capabilities.slice(0, 4).map((c) => (
                <span
                  key={c}
                  className="text-[10px] px-2 py-0.5 rounded-md bg-violet-500/10 text-violet-200 border border-violet-500/20"
                >
                  {c}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
