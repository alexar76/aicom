/** Data models for AI Market Protocol v2. */

export interface Capability {
  capability_id: string;
  product_id: string;
  name: string;
  version: string;
  description: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  price_per_call_usd: number;
  p50_latency_ms?: number;
  success_rate_30d?: number;
  source_hub: string;
  source_hub_name?: string;
  trust_score?: number;
}

export interface Channel {
  channel_id: string;
  deposit_usd: number;
  balance_usd: number;
  token: string;
  chain: string;
  expires_at: string;
}

export interface TeeAttestation {
  platform: string;
  enclave_id: string;
  code_hash: string;
  pcr_values: Record<string, string>;
  instance_id: string;
  region: string;
  timestamp: string;
  ttl_s: number;
  signature: string;
}

export interface TeeReceipt {
  receipt_id: string;
  input_hash: string;
  output_hash: string;
  signature: string;
}

export interface InvokeResult {
  success: boolean;
  output?: Record<string, unknown>;
  price_usd: number;
  latency_ms: number;
  safety_blocked: boolean;
  safety_reason?: string;
  tee_verified: boolean;
  tee_attestation?: TeeAttestation;
  tee_receipt?: TeeReceipt;
  error?: string;
}

export interface PlanStep {
  capability: Capability;
  relevance_score: number;
  rationale: string;
}

export interface Settlement {
  channel_id: string;
  total_spent_usd: number;
  refund_usd: number;
  invocations: number;
}

export interface BillOfMaterials {
  task: string;
  plan: PlanStep[];
  results: InvokeResult[];
  settlement?: Settlement;
  total_spent_usd: number;
  protocol_version: string;
}

export interface SearchResponse {
  results: PlanStep[];
  total: number;
  hub: string;
}
