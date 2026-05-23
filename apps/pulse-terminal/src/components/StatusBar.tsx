import type { PricingSnapshot } from '../lib/types';
import { fmtUsd } from '../lib/ui';

type Props = {
  snapshot: PricingSnapshot | null;
  latencyMs: number;
  listingCount: number;
};

export function StatusBar({ snapshot, latencyMs, listingCount }: Props) {
  const vol = snapshot?.listings.reduce((s, l) => s + l.share_price_usd, 0) ?? 0;
  return (
    <footer className="fixed bottom-0 left-0 right-0 z-40 border-t border-pulse-border bg-pulse-bg/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2 px-4 py-2 font-mono text-[10px] text-slate-500">
        <div className="flex gap-4">
          <span>ACEX {snapshot?.protocol_version ?? '—'}</span>
          <span>{listingCount} listings</span>
          <span>latency {latencyMs}ms</span>
        </div>
        <div className="flex gap-4">
          <span>Σ NAV {fmtUsd(vol, 0)}</span>
          <span className="text-pulse-gold">Pulse Terminal v0.1</span>
        </div>
      </div>
    </footer>
  );
}
