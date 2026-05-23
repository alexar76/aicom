import type { Listing } from '../lib/types';
import { Sparkline, cls, fmtNum, fmtUsd, shortId } from '../lib/ui';

type Props = {
  listings: Listing[];
  history: Record<string, number[]>;
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function ListingsTable({ listings, history, selectedId, onSelect }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-white/5 text-[10px] uppercase tracking-wider text-slate-500">
            <th className="pb-2 pr-4 font-medium">Listing</th>
            <th className="pb-2 pr-4 font-medium">CapShare</th>
            <th className="pb-2 pr-4 font-medium">Index</th>
            <th className="pb-2 pr-4 font-medium">IV</th>
            <th className="pb-2 pr-4 font-medium">Trust</th>
            <th className="pb-2 pr-4 font-medium">Route</th>
            <th className="pb-2 font-medium">Trend</th>
          </tr>
        </thead>
        <tbody>
          {listings.length === 0 && (
            <tr>
              <td colSpan={7} className="py-8 text-center text-slate-500">
                No listings — start factory pipeline or hub with capabilities
              </td>
            </tr>
          )}
          {listings.map((row) => {
            const sel = row.listing_id === selectedId;
            return (
              <tr
                key={row.listing_id}
                onClick={() => onSelect(row.listing_id)}
                className={cls(
                  'cursor-pointer border-b border-white/[0.03] transition hover:bg-white/[0.03]',
                  sel && 'bg-pulse-cyan/[0.06]',
                )}
              >
                <td className="py-3 pr-4">
                  <div className="font-mono text-xs text-pulse-cyan">{shortId(row.product_id)}</div>
                  <div className="text-[10px] text-slate-500">{row.capability_count} caps</div>
                </td>
                <td className="py-3 pr-4 font-mono text-white">{fmtUsd(row.share_price_usd, 3)}</td>
                <td className="py-3 pr-4 font-mono text-slate-200">{fmtNum(row.index_level, 1)}</td>
                <td className="py-3 pr-4">
                  <IvBadge iv={row.implied_volatility} />
                </td>
                <td className="py-3 pr-4 font-mono text-slate-300">{Math.round(row.avg_trust_score * 100)}%</td>
                <td className="py-3 pr-4">
                  <RouteBadge route={row.liquidity_route} />
                </td>
                <td className="py-3">
                  <Sparkline data={history[row.listing_id] ?? []} width={100} height={28} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function IvBadge({ iv }: { iv: number }) {
  const pct = Math.round(iv * 100);
  const hot = iv > 0.45;
  return (
    <span
      className={cls(
        'rounded px-1.5 py-0.5 font-mono text-[10px]',
        hot ? 'bg-pulse-amber/15 text-pulse-amber' : 'bg-white/5 text-slate-400',
      )}
    >
      {pct}%
    </span>
  );
}

function RouteBadge({ route }: { route: string }) {
  const jup = route === 'jupiter';
  return (
    <span
      className={cls(
        'rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide',
        jup ? 'border-violet-500/30 text-violet-300' : 'border-cyan-500/30 text-cyan-300',
      )}
    >
      {route}
    </span>
  );
}
