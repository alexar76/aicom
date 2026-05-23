import type { CapIndex, Listing, PricingSnapshot } from '../lib/types';
import { Gauge, Panel, Sparkline, fmtNum, fmtUsd } from '../lib/ui';

type Props = {
  listing: Listing | null;
  index: CapIndex | null;
  history: number[];
  capsense: PricingSnapshot['capsense'] | null;
  liquidity: PricingSnapshot['liquidity'] | null;
};

export function DetailRail({ listing, index, history, capsense, liquidity }: Props) {
  if (!listing) {
    return (
      <Panel title="Agent listing" subtitle="select row">
        <p className="text-sm text-slate-500">Choose a listing to inspect CapShare NAV, index components, and CapSense series.</p>
      </Panel>
    );
  }

  return (
    <div className="space-y-4">
      <Panel title={listing.product_id} subtitle="CapShare · revenue index">
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-500">CapShare NAV</p>
            <p className="font-display text-3xl font-bold text-white">{fmtUsd(listing.share_price_usd, 3)}</p>
          </div>
          <Sparkline data={history} width={140} height={44} stroke="#d4af37" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Metric label="Index level" value={fmtNum(listing.index_level, 2)} />
          <Metric label="IV" value={`${Math.round(listing.implied_volatility * 100)}%`} />
          <Metric label="$/call" value={fmtUsd(listing.avg_price_per_call_usd, 4)} />
          <Metric label="Success 30d" value={`${Math.round(listing.avg_success_rate_30d * 100)}%`} />
        </div>
        <div className="mt-4 space-y-3">
          <Gauge value={listing.avg_trust_score} label="Trust score" />
          <Gauge value={listing.avg_success_rate_30d} label="Reliability" />
        </div>
      </Panel>

      {index && (
        <Panel title="Index components" subtitle={index.index_id}>
          <ul className="space-y-2">
            {index.components.map((c) => (
              <li
                key={c.capability_id}
                className="flex items-center justify-between rounded-lg border border-white/5 bg-black/30 px-3 py-2 text-xs"
              >
                <span className="font-mono text-pulse-cyan">{c.capability_id}</span>
                <span className="text-slate-400">{(c.weight * 100).toFixed(0)}%</span>
                <span className="font-mono text-white">{fmtUsd(Number(c.price_per_call_usd), 3)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-right font-mono text-xs text-slate-500">
            24h {index.change_24h_pct >= 0 ? '+' : ''}
            {index.change_24h_pct.toFixed(2)}%
          </p>
        </Panel>
      )}

      {capsense?.enabled && (
        <Panel title="CapSense Options" subtitle="Phase 2 · Solana">
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Open series</span>
            <span className="font-mono text-pulse-gold">{capsense.open_series_count}</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Calls on revenue index · expiries{' '}
            {Array.isArray(capsense.series_template.expiry_days)
              ? (capsense.series_template.expiry_days as number[]).join(' / ')
              : '7 / 30 / 90'}
            d
          </p>
        </Panel>
      )}

      {liquidity && (
        <Panel title="Liquidity mesh" subtitle="routing">
          <pre className="overflow-x-auto rounded-lg bg-black/40 p-3 font-mono text-[10px] text-slate-400">
            {JSON.stringify(liquidity, null, 2)}
          </pre>
        </Panel>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className="font-mono text-sm text-white">{value}</p>
    </div>
  );
}
