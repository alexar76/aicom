import type { Agent } from '../lib/api';

export function MeshTopology({ agents }: { agents: Agent[] }) {
  const hub = { x: 50, y: 50, label: 'Mesh Core' };
  const nodes = agents.slice(0, 6);
  const positions = nodes.map((_, i) => {
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const r = 38;
    return { x: 50 + Math.cos(angle) * r, y: 50 + Math.sin(angle) * r };
  });

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <h2 className="font-display text-lg font-semibold text-white mb-4">
        Mesh topology
        {agents.length > 0 && (
          <span className="ml-2 text-sm font-normal text-slate-500">
            ({agents.length} verified peer{agents.length === 1 ? '' : 's'})
          </span>
        )}
      </h2>
      <svg viewBox="0 0 100 100" className="w-full aspect-square max-h-56">
        <defs>
          <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </radialGradient>
        </defs>
        {positions.map((p, i) => (
          <line
            key={`line-${i}`}
            x1={hub.x}
            y1={hub.y}
            x2={p.x}
            y2={p.y}
            stroke="rgba(34,211,238,0.25)"
            strokeWidth="0.4"
          />
        ))}
        <circle cx={hub.x} cy={hub.y} r="14" fill="url(#hubGlow)" />
        <circle cx={hub.x} cy={hub.y} r="6" fill="#22d3ee" />
        <text x={hub.x} y={hub.y + 18} textAnchor="middle" fill="#94a3b8" fontSize="4">
          {hub.label}
        </text>
        {nodes.map((a, i) => {
          const p = positions[i];
          return (
            <g key={a.id}>
              <circle cx={p.x} cy={p.y} r="5" fill="#a78bfa" opacity="0.9" />
              <text x={p.x} y={p.y + 11} textAnchor="middle" fill="#cbd5e1" fontSize="3.2">
                {a.name.split(' ')[0]}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="text-[11px] text-slate-500 mt-2 text-center">
        Zero-trust discovery routes tasks through verified peers
      </p>
    </div>
  );
}
