import type { Chain, PricingSnapshot } from './types';

const API = import.meta.env.VITE_PULSE_API_URL ?? '';

/** Abort hung factory pricing so the terminal never spins forever. */
export const PRICING_FETCH_TIMEOUT_MS = 12_000;

export function pricingHttpUrl(chain: Chain, limit = 50): string {
  const q = new URLSearchParams({ chain, limit: String(limit) });
  return `${API}/api/v2/capital/pricing?${q}`;
}

export function pricingWsUrl(chain: Chain, limit = 50): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = API ? new URL(API, location.origin).host : location.host;
  const q = new URLSearchParams({ chain, limit: String(limit) });
  return `${proto}//${host}/api/v2/capital/pricing/ws?${q}`;
}

export function pricingSseUrl(chain: Chain, limit = 50): string {
  const q = new URLSearchParams({ chain, limit: String(limit) });
  return `${API}/api/v2/capital/pricing/stream?${q}`;
}

export async function fetchPricing(chain: Chain, limit = 50): Promise<PricingSnapshot> {
  const r = await fetch(pricingHttpUrl(chain, limit), {
    signal: AbortSignal.timeout(PRICING_FETCH_TIMEOUT_MS),
  });
  if (!r.ok) throw new Error(`pricing ${r.status}`);
  return r.json();
}
