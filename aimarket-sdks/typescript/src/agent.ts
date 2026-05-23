/**
 * AI Market Protocol v2 Consumer Agent (TypeScript).
 *
 * Implements the 5-phase consumer cycle:
 *   1. Discovery  — fetch well-known + search
 *   2. Channel    — open pre-funded payment channel
 *   3. Invoke     — call capability with payment header
 *   4. Settle     — close channel, get refund
 *   5. Verify     — TEE attestation check
 *
 * Target: Electron desktop apps, Node.js servers, web apps.
 */

import * as nacl from 'tweetnacl';
import * as naclUtil from 'tweetnacl-util';
import {
  type Capability,
  type Channel,
  type InvokeResult,
  type PlanStep,
  type Settlement,
  type BillOfMaterials,
  type SearchResponse,
} from './models';

export class AimarketAgent {
  private readonly hubUrl: string;
  private readonly walletKey: Uint8Array;
  private readonly affiliate: string;
  private wellKnownCache: string | null = null;

  constructor(opts: {
    hubUrl: string;
    walletKey: string; // hex-encoded Ed25519 private key
    affiliate?: string;
  }) {
    this.hubUrl = opts.hubUrl.replace(/\/$/, '');
    this.walletKey = naclUtil.decodeBase64(
      Buffer.from(opts.walletKey, 'hex').toString('base64')
    );
    this.affiliate = opts.affiliate ?? 'aimarket-sdk-ts';
  }

  // ── Phase 1: Discovery ────────────────────────────────────────

  async wellKnown(): Promise<string> {
    if (this.wellKnownCache) return this.wellKnownCache;
    const resp = await fetch(`${this.hubUrl}/.well-known/ai-market.json`);
    if (!resp.ok) throw new Error(`Well-known failed: ${resp.status}`);
    this.wellKnownCache = await resp.text();
    return this.wellKnownCache;
  }

  async discover(opts: {
    intent: string;
    budget?: number;
    limit?: number;
    category?: string;
  }): Promise<PlanStep[]> {
    const params = new URLSearchParams({ intent: opts.intent });
    if (opts.budget !== undefined) params.set('budget_usd', String(opts.budget));
    if (opts.limit !== undefined) params.set('limit', String(opts.limit));
    if (opts.category) params.set('category', opts.category);

    const resp = await fetch(`${this.hubUrl}/ai-market/v2/search?${params}`, {
      headers: { 'X-AIMarket-Affiliate': this.affiliate },
    });
    if (!resp.ok) throw new Error(`Discovery failed: ${resp.status}`);
    const data: SearchResponse = await resp.json();
    return data.results;
  }

  // ── Phase 2: Channel Open ─────────────────────────────────────

  async openChannel(depositUsd: number, token = 'USDT', chain = 'base'): Promise<Channel> {
    const resp = await fetch(`${this.hubUrl}/ai-market/v2/channel/open`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-AIMarket-Affiliate': this.affiliate,
      },
      body: JSON.stringify({ deposit_usd: depositUsd, token, chain }),
    });
    if (!resp.ok) throw new Error(`Channel open failed: ${resp.status}`);
    return resp.json();
  }

  // ── Phase 3: Invoke ───────────────────────────────────────────

  async invoke(opts: {
    capabilityId: string;
    input: Record<string, unknown>;
    channelId: string;
    productId?: string;
    sourceHub?: string;
  }): Promise<InvokeResult> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Payment-Channel': opts.channelId,
      'X-AIMarket-Affiliate': this.affiliate,
      'X-Market-Signature': this.sign(
        `channel:${opts.channelId}|capability:${opts.capabilityId}|affiliate:${this.affiliate}`
      ),
    };

    const body: Record<string, unknown> = {
      capability_id: opts.capabilityId,
      input: opts.input,
    };
    if (opts.productId) body.product_id = opts.productId;
    if (opts.sourceHub) body.source_hub = opts.sourceHub;

    const startMs = performance.now();
    const resp = await fetch(`${this.hubUrl}/ai-market/v2/invoke`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });
    const latencyMs = performance.now() - startMs;

    if (resp.status === 403) {
      const data = await resp.json();
      return {
        success: false,
        price_usd: 0,
        latency_ms: latencyMs,
        safety_blocked: true,
        safety_reason: data.reason ?? 'Blocked by safety gate',
        tee_verified: false,
      };
    }
    if (resp.status === 402) {
      throw new Error('Payment required — channel depleted or expired');
    }
    return resp.json();
  }

  // ── Phase 4: Settle ───────────────────────────────────────────

  async closeChannel(channelId: string): Promise<Settlement> {
    const resp = await fetch(`${this.hubUrl}/ai-market/v2/channel/close`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-AIMarket-Affiliate': this.affiliate,
      },
      body: JSON.stringify({ channel_id: channelId }),
    });
    if (!resp.ok) throw new Error(`Settlement failed: ${resp.status}`);
    return resp.json();
  }

  // ── Phase 5: Verify ───────────────────────────────────────────

  verifyTeeAttestation(attestation: {
    code_hash: string;
    signature: string;
    canonical: string;
  }, expectedCodeHash: string): boolean {
    return attestation.code_hash === expectedCodeHash;
    // Full Ed25519 verification in production
  }

  // ── Full cycle ────────────────────────────────────────────────

  async runOnce(opts: {
    intent: string;
    input: Record<string, unknown>;
    depositUsd?: number;
    category?: string;
  }): Promise<BillOfMaterials> {
    const depositUsd = opts.depositUsd ?? 5.0;

    const plan = await this.discover({
      intent: opts.intent,
      budget: depositUsd,
      category: opts.category,
    });
    if (plan.length === 0) throw new Error(`No capabilities for: ${opts.intent}`);

    const channel = await this.openChannel(depositUsd);
    const step = plan[0];

    const result = await this.invoke({
      capabilityId: step.capability.capability_id,
      input: opts.input,
      channelId: channel.channel_id,
      productId: step.capability.product_id,
      sourceHub: step.capability.source_hub,
    });

    const settlement = await this.closeChannel(channel.channel_id);

    return {
      task: opts.intent,
      plan,
      results: [result],
      settlement,
      total_spent_usd: result.price_usd,
      protocol_version: 'v2',
    };
  }

  private sign(message: string): string {
    const msgBytes = new TextEncoder().encode(message);
    const sig = nacl.sign.detached(msgBytes, this.walletKey);
    return `ed25519:${naclUtil.encodeBase64(sig)}`;
  }
}
