export type Chain = 'any' | 'evm' | 'solana';

export type Listing = {
  listing_id: string;
  product_id: string;
  capability_count: number;
  share_price_usd: number;
  index_level: number;
  implied_volatility: number;
  avg_price_per_call_usd: number;
  avg_success_rate_30d: number;
  avg_trust_score: number;
  liquidity_route: string;
};

export type IndexComponent = {
  capability_id: string;
  weight: number;
  price_per_call_usd: number;
};

export type CapIndex = {
  index_id: string;
  listing_id: string;
  level: number;
  change_24h_pct: number;
  components: IndexComponent[];
};

export type PricingSnapshot = {
  protocol: string;
  protocol_version: string;
  generated_at: string;
  chain: string;
  listing_filter: string | null;
  listings: Listing[];
  indices: CapIndex[];
  liquidity: Record<string, unknown>;
  capsense: {
    enabled: boolean;
    chains: string[];
    series_template: Record<string, unknown>;
    open_series_count: number;
  };
  pulse_terminal: {
    refresh_ms: number;
    pricing_endpoint: string;
    hub_endpoint: string;
  };
};

export type ConnectionMode = 'websocket' | 'sse' | 'polling' | 'offline';
