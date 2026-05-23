import type { CapIndex } from '../lib/types';
import { fmtNum, fmtPct } from '../lib/ui';

export function TickerStrip({ indices }: { indices: CapIndex[] }) {
  if (!indices.length) return null;
  const items = [...indices, ...indices];

  return (
    <div className="relative overflow-hidden border-b border-pulse-border bg-black/50 py-2">
      <div className="animate-ticker flex w-max gap-8 whitespace-nowrap px-4">
        {items.map((idx, i) => {
          const up = idx.change_24h_pct >= 0;
          return (
            <div key={`${idx.index_id}-${i}`} className="flex items-center gap-3 font-mono text-xs">
              <span className="text-slate-400">{idx.index_id.replace('cap-revenue:', '')}</span>
              <span className="text-white">{fmtNum(idx.level, 1)}</span>
              <span className={up ? 'text-pulse-mint' : 'text-pulse-rose'}>{fmtPct(idx.change_24h_pct)}</span>
            </div>
          );
        })}
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-pulse-bg to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-pulse-bg to-transparent" />
    </div>
  );
}
