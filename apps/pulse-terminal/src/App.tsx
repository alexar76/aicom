import { useMemo, useState } from 'react';
import { Header } from './components/Header';
import { TickerStrip } from './components/TickerStrip';
import { ListingsTable } from './components/ListingsTable';
import { DetailRail } from './components/DetailRail';
import { StatusBar } from './components/StatusBar';
import { Panel } from './lib/ui';
import { usePricingStream } from './hooks/usePricingStream';
import type { Chain } from './lib/types';

export default function App() {
  const [chain, setChain] = useState<Chain>('any');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { snapshot, history, mode, error, latencyMs } = usePricingStream(chain);

  const listings = snapshot?.listings ?? [];
  const indices = snapshot?.indices ?? [];

  const selectedListing = useMemo(
    () => listings.find((l) => l.listing_id === selectedId) ?? listings[0] ?? null,
    [listings, selectedId],
  );

  const selectedIndex = useMemo(
    () => indices.find((i) => i.listing_id === selectedListing?.listing_id) ?? null,
    [indices, selectedListing],
  );

  const refreshMs = snapshot?.pulse_terminal.refresh_ms ?? 5000;

  return (
    <div className="terminal-grid min-h-screen pb-14">
      <Header
        chain={chain}
        onChain={setChain}
        mode={mode}
        generatedAt={snapshot?.generated_at ?? null}
        refreshMs={refreshMs}
      />
      <TickerStrip indices={indices} />

      {error && (
        <div className="mx-auto max-w-[1600px] px-4 pt-4">
          <div className="rounded-lg border border-pulse-rose/30 bg-pulse-rose/10 px-4 py-2 text-sm text-pulse-rose">
            {error} — ensure API at <code className="font-mono">/api/v2/capital/pricing</code> (factory :9081)
          </div>
        </div>
      )}

      <main className="mx-auto grid max-w-[1600px] gap-4 px-4 py-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="Agent listings" subtitle="CapShares · live NAV">
            <ListingsTable
              listings={listings}
              history={history}
              selectedId={selectedListing?.listing_id ?? null}
              onSelect={setSelectedId}
            />
          </Panel>
        </div>
        <DetailRail
          listing={selectedListing}
          index={selectedIndex}
          history={history[selectedListing?.listing_id ?? ''] ?? []}
          capsense={snapshot?.capsense ?? null}
          liquidity={snapshot?.liquidity ?? null}
        />
      </main>

      <StatusBar snapshot={snapshot} latencyMs={latencyMs} listingCount={listings.length} />
    </div>
  );
}
