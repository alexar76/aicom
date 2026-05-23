# Architecture: Creator Algorithm Coach

## Overview

The Creator Algorithm Coach is a Flutter desktop application that connects to the AI Market Protocol v2 to buy and sell algorithm optimization signals. The architecture is designed around three core systems:

1. **Platform Metrics Importer** — Ingests performance data from TikTok, YouTube, Instagram, and X
2. **Marketplace SDK** — Discovers, purchases, and invokes algorithm signal capabilities
3. **TEE Verification Layer** — Client-side attestation that traded data was generated in a Trusted Execution Environment

## System Architecture Diagram

```
┌────────────────────────────────────────────────────────────┐
│  Creator Algorithm Coach (Flutter Desktop)                  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Dashboard    │  │  Discover    │  │  Insights    │      │
│  │  Screen      │  │  Screen     │  │  Screen     │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │              │
│  ┌──────┴─────────────────┴─────────────────┴───────┐      │
│  │              AppState (Provider)                   │      │
│  │  - activePlatform, niche, budgetUsd                │      │
│  │  - marketplaceConnection, walletAddress            │      │
│  └───────────────────────┬───────────────────────────┘      │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────┐      │
│  │           MarketplaceService                       │      │
│  │  ┌─────────────────────────────────────────────┐  │      │
│  │  │  AimarketAgent (aimarket_agent Dart SDK)     │  │      │
│  │  │  - discover(intent, budget, category)        │  │      │
│  │  │  - openChannel(depositUsd)                   │  │      │
│  │  │  - invoke(capabilityId, input, channelId)    │  │      │
│  │  │  - closeChannel(channelId)                   │  │      │
│  │  │  - verifyTeeAttestation()                    │  │      │
│  │  │  - verifyTeeReceipt()                        │  │      │
│  │  └─────────────────────────────────────────────┘  │      │
│  └────────────────────────────────────────────────────┘      │
│                                                             │
│  ┌────────────────────────────────────────────────────┐      │
│  │  TEE Verifier                                       │      │
│  │  - Verifies attestation before sending data         │      │
│  │  - Verifies receipt after receiving output          │      │
│  │  - Maintains trusted code hash registry             │      │
│  └────────────────────────────────────────────────────┘      │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTPS + Signed Headers
                           ▼
┌────────────────────────────────────────────────────────────┐
│  AI Market Hub (hub.aicom.io)                              │
│                                                             │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  Discovery API  │  │  Invoke API    │  │  Channel API │  │
│  │  /v2/search     │  │  /v2/invoke    │  │  /v2/channel │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
│                                                             │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  Capability     │  │  Payment       │  │  Safety Gate │  │
│  │  Registry       │  │  Ledger        │  │              │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────┐
│  Decentralized Signal Providers                               │
│                                                             │
│  TikTok Analysts   TrendWatchers   CreatorDAO   Platform    │
│  (specialist)      DAO (trends)    (hooks)       Signals Inc.│
│                                                             │
│  Each provider runs capabilities with TEE attestation:       │
│  - TEE simulation for development (AWS Nitro/TDX in prod)    │
│  - Code hash verified at invocation                          │
│  - Every output includes an attestation receipt (alpha)      │
└─────────────────────────────────────────────────────────────┘
```

## 1. Platform Metrics Importer

The Metrics Importer handles ingestion of performance data from four platforms:

### TikTok
- **Source**: TikTok Analytics export (CSV/JSON), TikTok API (with user token)
- **Signals**: Watch time by time-of-day, completion rate by video length, sound trend velocity, hook retention curves
- **Decay**: 7-day TTL — TikTok algorithm shifts weekly

### YouTube
- **Source**: YouTube Studio API, channel CSV export
- **Signals**: CTR by thumbnail type, audience retention by format, search ranking shifts, Shorts-to-long conversion
- **Decay**: 14-day TTL — YouTube changes are slower but impactful

### Instagram
- **Source**: Instagram Insights API, meta business suite export
- **Signals**: Reel engagement by audio, carousel vs reel preference, explore page ranking factors
- **Decay**: 7-day TTL — Instagram experiments frequently

### X / Twitter
- **Source**: X API v2, analytics CSV
- **Signals**: Reply-to-impression ratio, trending topic velocity, thread engagement patterns
- **Decay**: 3-day TTL — X algorithm changes most rapidly

### Importer Pipeline

```
Raw Data → Normalizer → Signal Extractor → TEE Attestation → Marketplace Listing
```

Each stage:
1. **Raw Data** — Platform export or API response
2. **Normalizer** — Converts platform-specific formats to canonical schema
3. **Signal Extractor** — Computes metrics (optimal times, trend windows, hook scores)
4. **TEE Attestation** — Signs the computed output inside an enclave
5. **Marketplace Listing** — Published as a capability on the AI Market hub

## 2. Marketplace SDK for Buying Signals

The consumer flow follows the **5-phase protocol cycle** defined in `aimarket_agent`:

### Phase 1: Discovery
```
GET /ai-market/v2/search?intent=<nl-description>&budget_usd=<amount>&category=creator
```

The app sends a natural-language intent like `"algorithm signals for tiktok cooking niche - optimal posting times"`. The hub returns ranked `PlanStep` objects — each containing a `Capability` with price, trust score, and TEE status.

### Phase 2: Channel Open
```
POST /ai-market/v2/channel/open
{"deposit_usd": 5.00, "token": "USDT", "chain": "base"}
```

A pre-funded payment channel is opened. This covers ~50 invocations at \$0.10 each. Unused balance is refunded on close.

### Phase 3: Invoke
```
POST /ai-market/v2/invoke
Headers: X-Payment-Channel, X-Market-Signature, X-AIMarket-Affiliate
Body: {"capability_id": "...", "input": {...}}
```

The invoke call includes payment headers signed with the wallet key. The hub deducts from the channel balance per-call.

### Phase 4: Settle
```
POST /ai-market/v2/channel/close
{"channel_id": "..."}
```

Closes the channel and returns remaining balance as a refund.

### Phase 5: Verify
Client-side TEE verification proves:
- The capability ran in an attested enclave (pre-invoke check)
- The output was generated inside that enclave (post-invoke receipt check)

## 3. TEE for Selling Verified Performance Data

The key insight: **unverified creator metrics are worthless** because anyone can fake engagement data. TEE attestation solves this.

### Seller Flow

1. **Creator** imports their platform analytics into the app
2. **Metrics Importer** normalizes and extracts signals
3. **TEE Attestation** signs the output with enclave proof:
   ```json
   {
     "tee_attestation": {
       "platform": "aws_nitro",
       "enclave_id": "eni-abc123",
       "code_hash": "sha256:abc...",
       "pcr_values": {"pcr0": "..."},
       "timestamp": "2026-05-23T00:00:00Z",
       "ttl_s": 300,
       "signature": "ed25519:..."
     },
     "metrics": {
       "platform": "tiktok",
       "niche": "cooking",
       "avg_watch_time": 23.5,
       "hook_ctr": 0.68,
       "optimal_posting_time": "14:14 EST"
     }
   }
   ```
4. **Marketplace listing** — the attested metrics become a purchasable capability
5. **Buyers** can verify the TEE receipt before trusting the data

### TEE Verification Client-Side

```dart
// Pre-invoke: verify the capability runs in a trusted enclave
bool enclaveTrusted = agent.verifyTeeAttestation(
  attestation,
  capabilityId,
);

// Post-invoke: verify output was generated inside the enclave
bool outputVerified = agent.verifyTeeReceipt(
  receipt,
  sentInput,
  receivedOutput,
);
```

## Data Flow for Tier 3 Decay

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Provider  │───▶│  Market  │───▶│ Consumer │
│ captures  │    │  hub     │    │  buys    │
│ real-time │    │  indexes │    │  signal  │
│ metrics   │    │  with TTL│    │          │
└──────────┘    └──────────┘    └──────────┘
     │               │               │
     │ 7-day TTL     │ auto-expire   │ re-buy
     ▼               ▼               ▼
  New data        Stale entry     Fresh signal
  replaces        removed from    replaces old
  old             search          on next cycle
```

Tier 3 means:
- Signal providers must re-attest data every 7 days or it expires
- Consumers get fresh data but pay a lower price per call (\$0.10–\$0.30)
- The marketplace automatically hides expired capabilities from search
- This creates a recurring revenue loop for accurate providers

## Security Model

| Layer | Mechanism |
|-------|-----------|
| Wallet key | Ed25519/HMAC-SHA256 signatures on device |
| Transport | HTTPS with signed headers |
| Capability safety | Hub safety gate (403 on dangerous inputs) |
| Data confidentiality | TEE encryption — decrypted only inside enclave |
| Output integrity | TEE receipt with input/output hash |
| Trust registry | Hardcoded known-good code hashes + hub registry |
