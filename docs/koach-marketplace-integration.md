# Koach × AIMarket — Integration Blueprint

**Profile Coach as the first reference desktop client in the aicom economy.**

---

## 1. Strategic Context

### Why Desktop > Web for Marketplace Economy

Desktop apps have two structural advantages over web apps in the aicom economy:

1. **Long-lived state** — local SQLite, files, auto-start. A desktop app can hold payment channels open for days, cache capabilities offline, and run background agents. Web tabs get closed.

2. **Local compute** — Whisper, local LLM, file parsers. Desktop apps can SELL their local capabilities to the network (p2p-adjacent), not just buy from it.

This means **three roles instead of two** — desktop apps can be consumers, providers, AND products of the factory.

### Three Ways to Embed the Economy in Desktop

```
Role 1: BUYER (consumer)          Role 2: SELLER (provider)        Role 3: PRODUCT (factory output)
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│ Figma-like editor   │      │ Local Whisper        │      │ aicom generates     │
│ buys "brand styling │      │ sells transcription  │      │ Electron/Tauri      │
│ template" for $0.10 │      │ to neighbors via hub │      │ bundle → listed as  │
│                     │      │                     │      │ desktop_app in hub  │
│ IDE buys code-review│      │ Koach sells scoring  │      │                     │
│ agent per project   │      │ agent as capability  │      │ User buys desktop   │
│                     │      │                     │      │ app license via hub │
│ CAD buys converter  │      │ Local GPU sells      │      │                     │
│ via mcp-packager    │      │ inference slots      │      │ Auto-update via hub │
└─────────────────────┘      └─────────────────────┘      └─────────────────────┘
```

Koach naturally occupies **all three** roles — it's the perfect reference implementation.

### What Koach already has

Koach is a Flutter desktop app (macOS/Windows/Linux) that:
- Imports 24 LinkedIn profile sections via ZIP/JSON/Chrome extension/URL
- Has a pluggable LLM provider system: DeepSeek, OpenAI, Anthropic, Ollama, LM Router — each with its own preset
- Runs ATS scoring (keyword-based + LLM evaluator) with a local template fallback
- Exports to DOCX, publishes back to LinkedIn
- Manages multiple profiles per user

The LLM provider system is the integration slot. Adding `aimarket://` as a provider is ~500 lines of Dart — a thin REST client that speaks Protocol v2.

### Why this matters for aicom

Koach is not a pet project. It has:
- **Installed users** — even 10 is validation that the pain is real
- **Real pain** — LinkedIn has no write API. Everything is manual copy-paste. Users will pay for magic.
- **Architecture fit** — the provider slot means marketplace doesn't break anything, it pours into an existing slot
- **Cross-platform Flutter** — the first reference client on 4 OSes immediately
- **Narrative power** — "a third-party app became the first buyer in our economy" is stronger than any whitepaper

---

## 2. Three Surfaces = Three Economic Roles

### 2.1 Koach as Buyer (Phase 1 — 1-2 weeks)

What Koach lacks today — and what the marketplace solves better than any subscription:

| Capability | Current State | Marketplace Solution | Price Point |
|---|---|---|---|
| ATS rules (Workday/Greenhouse/Lever) | Stale Dart code, rots every quarter | One maintainer updates `ats-rules-2026-Q2`, all coaches buy fresh rules monthly | ~$0.10/refresh |
| Industry datasets | None — no data on "what fintech recruiters read in Q2 2026" | Data-capability plugins with anonymized aggregates | ~$0.50/query |
| Benchmark profiles | None — can't tell user they're top 1% | Anonymized top-percentile profiles by niche | ~$0.25/benchmark |
| Salary signals | None — can't tie score to market value | Market-rate capability keyed to role × industry × locale | ~$0.25/lookup |
| Locale norms | None — RU/EU/US norms differ radically | Per-locale rule packs maintained by local experts | ~$0.10/pack |
| Recruiter personas | None — "what Google recruiter reads" vs "startup recruiter" | Persona-specific scoring weights | ~$0.10/persona |

All of these are **classic marketplace goods**: decentralized maintenance, fast-rotting data, everyone benefits from one source.

### 2.2 Koach as Seller (Phase 2 — 1-2 months)

After a year of usage, Koach has thousands of profile scoring runs. Anonymized aggregates are sellable:

| Product | Description |
|---|---|
| Bullet pattern insights | "Phrases like 'led X achieving Y' score +20% ATS in tech roles" |
| AI Profile Generator | The writing capability itself, packaged as an MCP tool |
| Scoring Agent | Standalone ATS evaluator, sold through `mcp-packager` plugin |
| LinkedIn Data Extractor | Chrome extension + ZIP parser, nontrivial to replicate |
| DOCX Pipeline | Resume export — small but useful for HR SaaS |

The **tee plugin** is critical here: users must be able to verify that purchased scoring doesn't leak their profile data. Without TEE attestation, this doesn't work.

### 2.3 Koach as Discovery Probe (Phase 3 — 3-6 months)

Koach sits on real-time pain signals from professionals. The aicom Discovery agent pays for this data. Koach becomes:

- **Retailer** for end users (the app they use daily)
- **Wholesaler** for other apps (HR SaaS vendors embed Koach SDK)
- **Node** in the marketplace (orchestrates writing-agent → scoring-agent → ATS-checker, each bought from different sellers)

---

## 3. SDK Port Strategy

The protocol is universal (JSON/HTTP) — it works for any platform. What's missing is language-native SDKs:

| Layer | Current | Desktop Gap |
|---|---|---|
| Protocol (v2) | JSON/HTTP | Works as-is, transport is universal |
| Agent (consumer) | Python CLI (`cli/ai_market_agent.py`) | Need: TS for Electron, Dart for Flutter, Rust for Tauri |
| Widget (storefront) | HTML/JS (`aimarket-widget/`) | Works in Electron immediately. Native (Flutter/Qt) needs rewrite |
| Payment | Web wallet | Desktop deep-link → browser → signature → callback (Metamask pattern) |

### Fastest path: Electron + existing widget

Wrap `aimarket-widget` in an Electron window, add `aimarket://` deep-link handler for payments. One hour of work = desktop marketplace client.

### Most interesting path: Koach (Flutter) + Dart SDK port

Koach already runs natively on macOS/Windows/Linux via Flutter. A Dart port of `aimarket-agent` (~500 lines) turns it from a standalone tool into the first reference desktop client of the economy. This is what Phase 1 implements.

### Generic SDK surface (to extract from Koach after validation)

```dart
// Published as aimarket_agent on pub.dev after Koach validates it
class AimarketAgent {
  /// Discover capabilities matching intent
  Future<List<Capability>> discover({required String intent, double? budget, int? limit});
  
  /// Open pre-funded payment channel
  Future<Channel> openChannel(double depositUsd);
  
  /// Invoke capability, paying from channel
  Future<InvokeResult> invoke({required String capabilityId, required Map<String, dynamic> input, required String channelId});
  
  /// Settle and close channel
  Future<Settlement> closeChannel(String channelId);
  
  /// Verify TEE attestation locally
  bool verifyTee(TEEAttestation attestation, String expectedCodeHash);
}

// Also used by any Flutter desktop app, not just Koach
```

---

## 4. Phase 1 Implementation — Koach as Buyer

### 3.1 Marketplace Taxonomy Update

**File:** `marketplace_taxonomy.py`

Added `"career"` category alongside the existing 8:

```python
MARKETPLACE_CATEGORY_IDS = (
    "ai_ml", "devtools", "fintech", "saas",
    "ecommerce", "iot", "security", "productivity",
    "career",  # ← NEW
)
```

Aliases: `career`, `hiring`, `recruitment`, `hr`, `human_resources`, `jobs`, `job_search`, `resume`, `cv`, `linkedin`, `interview`.

Keyword inference: `resume`, `cv`, `job search`, `recruit`, `hiring`, `career coach`, `linkedin profile`, `ats`, `interview prep`, `salary benchmark`, `headline`, `cover letter`, `job board`, `applicant tracking`.

**File:** `web/backend/api/products.py`

Added storefront category entry:
```python
{"id": "career", "name": "Career", "icon": "briefcase",
 "description": "Career coaching, resume tools, job search"},
```

### 3.2 Dart AIMarket Agent (aimarket-agent port)

New file: `coach/lib/services/aimarket/aimarket_agent.dart`

Thin REST client (~500 lines) implementing Protocol v2 consumer:

```
┌─────────────────────────────────────────┐
│         AIMarketAgent (Dart)            │
│                                         │
│  discover(intent, budget, limit)        │
│    → GET /.well-known/ai-market.json    │
│    → GET /ai-market/v2/search           │
│    → returns List<Capability>           │
│                                         │
│  openChannel(depositUsd)                │
│    → POST /ai-market/v2/channel/open    │
│    → returns channelId                  │
│                                         │
│  invoke(capabilityId, input, channelId) │
│    → POST /ai-market/v2/invoke          │
│    → Headers: X-Payment-Channel,        │
│               X-AIMarket-Affiliate      │
│    → returns output + receipt           │
│                                         │
│  closeChannel(channelId)                │
│    → POST /ai-market/v2/channel/close   │
│    → returns settlement                 │
│                                         │
│  verifyTeeAttestation(attestation)      │
│    → validates code_hash + signature    │
│    → checks expiry (5 min TTL)          │
└─────────────────────────────────────────┘
```

Key design decisions:
- Uses Dart `http` package (already in pubspec.yaml)
- Signing via `ed25519` or `p256` — reuses hub's canonical signing format
- All calls go to the user's chosen hub (default: aicom hub, self-hostable)
- Affiliate header = `"koach"` for discovery credit

### 3.3 Provider Registration in LLM System

**File:** `coach/lib/models/ai_settings.dart`

Add the `aimarket` provider to the enum:

```dart
enum AiProvider {
  deepseek,
  openai,
  openAiCompatible,
  anthropic,
  lmrouter,
  ollama,
  aimarket,  // ← NEW
}
```

Add preset:

```dart
AiProvider.aimarket: AiProviderPreset(
  label: 'AI Market',
  baseUrl: 'https://hub.aicom.io',  // default hub
  defaultModel: 'market/best',       // semantic: "best available"
  needsApiKey: false,                // wallet-based auth, not API key
  hint: 'Pay-per-call marketplace. Credits via wallet, not API key.',
),
```

**File:** `coach/lib/services/llm/llm_service.dart`

Add routing case:

```dart
if (settings.provider == AiProvider.aimarket) {
  final agent = AimarketAgent(
    hubUrl: settings.effectiveBaseUrl,
    walletKey: settings.apiKey,  // repurposed: stores wallet private key
  );
  return agent.complete(
    system: system,
    user: user,
    temperature: temperature,
  );
}
```

Note: The `apiKey` field is repurposed for `aimarket` — instead of an API key, it stores the user's wallet private key (or a session token derived from it). This avoids adding new fields to `AiSettings` in Phase 1.

### 3.4 Marketplace Screen in Settings

**File:** `coach/lib/screens/shell_screen.dart`

Add navigation entry:

```dart
(Icons.store_outlined, l10n.navMarketplace),  // position 8
```

New screen: `coach/lib/screens/marketplace_screen.dart`

Contains:
- **Catalog browser** — filtered to `career` category by default, searchable
- **Credits balance** — shows remaining credits (fetched from hub)
- **Purchase history** — list of bought capabilities with expiration
- **Top-up button** — deep-link to browser wallet: `aimarket://pay?invoice=...`

### 3.5 Deep-Link Payment Flow

```
User taps "Update ATS Rules ($0.10)"
         │
         ▼
Koach → Hub: POST /ai-market/v2/channel/open {deposit: 5.00}
         │
         ▼
Hub returns: {channel_id, invoice_url: "aimarket://pay?invoice=inv_abc123"}
         │
         ▼
Koach opens browser: https://hub.aicom.io/pay?invoice=inv_abc123
         │
         ▼
User approves wallet tx (Base chain, USDT)
         │
         ▼
Hub confirms on-chain → channel funded
         │
         ▼
Browser → Koach callback: coach://marketplace/callback?channel=ch_xyz&status=funded
         │                    (custom URL scheme registered by Flutter app)
         ▼
Koach invokes capability, debits from channel
```

The Flutter app registers `coach://` as a custom URL scheme on all platforms. The payment callback returns the user to the app with the channel ready.

### 3.6 First Purchase Scenario: ATS Rules Refresh

```
1. User opens Marketplace tab
2. Sees "ATS Rules 2026 Q2" — $0.10 (seller: @ats-maintainer)
3. Taps "Buy & Apply"
4. Koach opens $5.00 channel (covers ~50 refreshes)
5. User confirms wallet tx in browser
6. Koach invokes capability:
     POST /ai-market/v2/invoke
     {
       "product_id": "ats-rules-workday",
       "capability_id": "refresh-2026-q2",
       "input": {"target_role": "Senior PM", "target_industry": "fintech"}
     }
7. Returns: {keywords: [...], weights: {...}, rules: [...]}
8. Koach stores in local SQLite, marks "fresh until 2026-07-01"
9. ATS scoring now uses live rules instead of stale Dart code
```

Success metric: **how many times user taps "Refresh ATS Rules"** — this is the north star for Phase 1.

---

## 5. TEE & Privacy Architecture

### Why TEE is a blocker

If a user buys "ATS Scoring" from the marketplace, the capability runs on the seller's hub. The seller's hub receives the user's **LinkedIn profile text** as input. Without TEE attestation, the user has no proof the seller isn't:
- Storing the profile
- Training on it
- Selling it to recruiters

This is not a nice-to-have. It's a blocker for Phase 1.

### TEE Attestation Flow

```
┌──────────┐     ┌──────────────┐     ┌──────────────────┐
│  Koach   │     │  Seller Hub  │     │  TEE Enclave     │
│ (buyer)  │     │              │     │  (Nitro/TDX)     │
└────┬─────┘     └──────┬───────┘     └────────┬─────────┘
     │                   │                      │
     │ 1. GET /manifest  │                      │
     │──────────────────▶│                      │
     │                   │                      │
     │ 2. manifest includes                      │
     │    tee_attestation: {                      │
     │      platform: "aws_nitro",                │
     │      code_hash: "sha256:abc123...",        │
     │      pcr_values: {...},                    │
     │      signature: "ed25519:xyz..."           │
     │    }                                       │
     │◀──────────────────│                      │
     │                   │                      │
     │ 3. Verify attestation locally:            │
     │    - code_hash matches known good         │
     │    - signature from enclave key valid     │
     │    - not expired (< 5 min old)            │
     │                   │                      │
     │ 4. POST /invoke with encrypted input      │
     │    (encrypted to enclave public key)      │
     │──────────────────▶│                      │
     │                   │   5. Forward to enclave
     │                   │──────────────────────▶│
     │                   │                      │
     │                   │   6. Enclave decrypts,
     │                   │      runs scoring,
     │                   │      encrypts output
     │                   │◀──────────────────────│
     │                   │                      │
     │ 7. Output + tee_receipt:                  │
     │    {result: {...},                        │
     │     receipt: {                            │
     │       receipt_id: "...",                  │
     │       input_hash: "sha256:...",           │
     │       output_hash: "sha256:...",          │
     │       signature: "ed25519:..."            │
     │    }}                                     │
     │◀──────────────────│                      │
     │                   │                      │
     │ 8. Verify receipt:                        │
     │    - input_hash = sha256(what we sent)    │
     │    - signature from enclave key valid     │
     │    - receipt_id is fresh                  │
     │                   │                      │
     │ 9. Koach displays:                        │
     │    "✓ ATS scored in secure enclave"       │
     │    "  Code: sha256:abc123"                │
     │    "  Platform: AWS Nitro"                │
```

The existing `tee_attestation.py` in the hub already implements this. The TEE plugin (`plugins/aimarket-tee/`) provides the hooks. The Dart agent just needs to verify the attestation locally (Step 3) and the receipt (Step 8).

### Privacy Guarantee

The data flow is **one-way**: capabilities and data flow INTO Koach, the profile never flows OUT to the marketplace for scoring.

For data-capability queries (e.g., "what are fintech recruiters reading in Q2 2026"), the query is a search — the profile is not sent. The capability returns aggregate data.

For scoring capabilities, the profile IS sent as input — which is why TEE is required. The user sees: "This scorer runs in AWS Nitro. Code hash verified. Your profile is decrypted only inside the enclave and destroyed after scoring."

---

## 5. Payment UX

### The $0.05 Problem

Nobody clicks "Pay $0.05" before every action. The solution:

**Pre-funded credits model:**
1. User tops up wallet once (e.g., $20 = 200 credits at $0.10 avg)
2. Each marketplace call deducts from channel balance
3. Koach shows: "ATS Rules: $0.10 (200 credits remaining)"
4. No confirmation dialog for calls under $0.50
5. Channel auto-renews when balance drops below $2.00

**Monthly subscription wrapper:**
- "Career Pro" — $9.99/month, includes 50 marketplace calls
- Overages billed at standard marketplace rates
- This is a Koach-level feature, not marketplace — the marketplace only sees pay-per-call

### Wallet Integration

Koach reuses the existing aicom wallet infrastructure:
- **Chain:** Base (low gas)
- **Token:** USDT
- **Wallet address:** user gets a derived wallet or connects existing
- **Top-up:** deep-link to hub's payment page
- **Balance:** fetched from hub on app start + after each purchase

---

## 6. Phase 2 — Koach as Seller

### Opt-in Data Sharing

```
┌─────────────────────────────────────────────┐
│  "Share anonymized insights, earn credits"  │
│                                             │
│  ☐ Share aggregate scoring patterns         │
│     (NO profile text, NO personal data)     │
│                                             │
│  ☐ Share improvement metrics                │
│     ("my score went from 62 → 84")          │
│                                             │
│  ☐ Publish successful patterns to hub       │
│     ("these bullet templates worked")        │
│                                             │
│  [Verified by TEE: data is anonymized       │
│   before leaving your device]               │
│                                             │
│  You earn: ~$2.00/month in credits          │
└─────────────────────────────────────────────┘
```

The `tee` plugin verifies that anonymization happens client-side before any data leaves Koach. This is trust-critical — if users suspect their profile data is being sold, they leave.

### Publishing Flow

1. User runs ATS scoring, gets score improvement (e.g., +22%)
2. Koach detects this as a "successful improvement"
3. Koach asks: "Your bullet pattern improved ATS by 22%. Publish anonymized pattern for $0.50 credit?"
4. User approves → pattern is anonymized client-side → published to hub with `career` category
5. Other coaches (and any app) can buy this pattern

### MCP Packaging

The Scoring Agent and AI Profile Generator are packaged as MCP tools via the `aimarket-mcp-packager` plugin:

```json
{
  "name": "koach-scoring-agent",
  "description": "ATS-compatible LinkedIn profile scorer. Evaluates 24 sections against ATS rules for Workday, Greenhouse, Lever.",
  "input_schema": {
    "type": "object",
    "properties": {
      "profile_json": {"type": "object", "description": "24-section LinkedIn profile"},
      "target_role": {"type": "string"},
      "target_industry": {"type": "string"},
      "ats_system": {"type": "string", "enum": ["workday", "greenhouse", "lever", "all"]}
    }
  },
  "price_per_call_usd": 0.05
}
```

Any MCP-compatible app can now call Koach's scorer without knowing what Koach is.

---

## 7. Phase 3 — Koach as Network Node

### Koach as a Hub Listing

Koach itself becomes a listing in the hub:

```json
{
  "product_id": "koach",
  "name": "LinkedIn Profile Coach",
  "category": "career",
  "capabilities": [
    {"id": "scoring", "price_usd": 0.05},
    {"id": "ai-generate", "price_usd": 0.10},
    {"id": "import-linkedin", "price_usd": 0.02},
    {"id": "benchmark", "price_usd": 0.25}
  ],
  "well_known_url": "https://koach.app/.well-known/ai-market.json"
}
```

### HR SaaS Embedding

HR platforms embed Koach SDK to offer LinkedIn optimization as a feature:

```dart
// In any Flutter app
import 'package:koach_sdk/koach_sdk.dart';

final coach = KoachSDK(apiKey: '...');
final score = await coach.scoreProfile(
  profile: userProfile,
  targetRole: 'Engineering Manager',
  atsSystem: 'greenhouse',
);
```

Koach SDK internally calls marketplace capabilities, each from potentially different sellers. Koach becomes the retailer for end users and the wholesaler for other apps.

### Internal Orchestration

When a user clicks "Full Analysis," Koach orchestrates:

```
User Profile
     │
     ├──▶ writing-agent (bought from seller A, $0.10)
     │    → generates AI profile variant
     │
     ├──▶ scoring-agent (bought from seller B, $0.05)
     │    → scores both current and AI versions
     │
     ├──▶ ats-checker (bought from seller C, $0.10)
     │    → verifies against Workday/Greenhouse rules
     │
     ├──▶ benchmark (bought from seller D, $0.25)
     │    → compares to top-1% in niche
     │
     └──▶ salary-signal (bought from seller E, $0.25)
          → estimates market value from score
```

Total: $0.75 for a full analysis. Koach takes 15% margin ($0.11), sellers get $0.64. The user sees "Full Analysis — $0.75 (182 credits remaining)."

---

## 8. Files to Create / Modify

### aicom side (this repo)

| File | Action | Description |
|---|---|---|
| `marketplace_taxonomy.py` | **DONE** | Added `career` category + aliases + keywords |
| `web/backend/api/products.py` | **DONE** | Added `career` storefront category entry |
| `web/frontend/lib/categories.ts` | Modify | Add `career` to frontend category list |
| `data/hub/` | Seed | Add career-specific capabilities (ATS rules, benchmarks, etc.) |
| `docs/koach-marketplace-integration.md` | **DONE** | This document |

### Koach side (coach repo)

| File | Action | Description |
|---|---|---|
| `lib/models/ai_settings.dart` | Modify | Add `aimarket` to `AiProvider` enum + preset |
| `lib/services/llm/llm_service.dart` | Modify | Add routing for `AiProvider.aimarket` |
| `lib/services/aimarket/aimarket_agent.dart` | **Create** | Protocol v2 consumer (~500 lines) |
| `lib/services/aimarket/aimarket_signer.dart` | **Create** | Ed25519 signing for hub requests |
| `lib/services/aimarket/tee_verifier.dart` | **Create** | Local TEE attestation verification |
| `lib/screens/marketplace_screen.dart` | **Create** | Marketplace catalog + purchase history |
| `lib/screens/shell_screen.dart` | Modify | Add "Marketplace" nav tab |
| `lib/widgets/marketplace_catalog.dart` | **Create** | Catalog browser widget |
| `lib/widgets/marketplace_credits.dart` | **Create** | Credits balance widget |
| `lib/l10n/app_en.arb` | Modify | Add marketplace strings |
| `lib/l10n/app_ru.arb` | Modify | Add marketplace strings (Russian) |
| `lib/l10n/app_es.arb` | Modify | Add marketplace strings (Spanish) |
| `lib/database/database_helper.dart` | Modify | Add marketplace tables (purchases, channels) |
| `pubspec.yaml` | Modify | Add `ed25519` or crypto dep if needed |

---

## 9. Localization Keys to Add

```json
// app_en.arb additions
"navMarketplace": "Marketplace",
"marketplaceCatalogTitle": "Career Marketplace",
"marketplaceCreditsBalance": "{count, plural, =0{No credits} =1{1 credit} other{{count} credits}}",
"marketplaceBuy": "Buy & Apply",
"marketplaceRefresh": "Refresh",
"marketplaceTopUp": "Top up credits",
"marketplaceNoResults": "No capabilities found for your profile",
"marketplaceTeeVerified": "TEE-verified",
"marketplacePurchased": "Purchased",
"marketplaceExpires": "Expires {date}",
"marketplaceChannelFunded": "Channel funded: {amount}",
"marketplaceCategoryCareer": "Career",
"marketplaceCategoryAll": "All categories",
"aiProviderAimarket": "AI Market",
"aiProviderAimarketHint": "Pay-per-call marketplace. Top up credits in Marketplace tab.",
"aiProviderAimarketSetupHint": "AI Market: hub.aicom.io — wallet-based, no API key. Top up credits first.",
"aiGenViaMarketplace": "Generated via marketplace ({provider})",
"marketplacePrivacyNotice": "Your profile is never sent to the marketplace. Only anonymized queries leave your device.",
"marketplaceTeeNotice": "This capability runs in a secure enclave. Input is encrypted and destroyed after use.",
"marketplaceOptInShareTitle": "Share insights, earn credits",
"marketplaceOptInShareDesc": "Anonymized scoring patterns help other professionals. You earn credits for each published pattern.",
```

---

## 10. Success Metrics

### Phase 1
- **Users who tap "Refresh ATS Rules" at least once:** target > 30% of active users
- **Average monthly spend per user:** target > $1.00
- **Repeat purchase rate:** target > 40% buy a second capability within 30 days

### Phase 2
- **Opt-in rate for data sharing:** target > 20% of active users
- **Published patterns from Koach users:** target > 50 in first 60 days
- **External buyers of Koach patterns:** target > 5 unique buyer apps

### Phase 3
- **HR SaaS integrations:** target > 2 platforms
- **Koach as % of total marketplace volume:** target > 5%
- **New users who discover marketplace through Koach:** target > 100

---

## 11. What Must Not Be Broken

1. **Privacy** — LinkedIn data is PII. The flow is always one-way: capabilities/data flow INTO Koach, profiles never flow OUT for scoring without TEE. The marketplace buys templates and rules, it does not receive profiles.

2. **TEE Verification** — Without the `tee` plugin, users cannot trust that a purchased scorer isn't exfiltrating profile data. This is a blocker for Phase 1, not a nice-to-have.

3. **Payment UX** — Nobody clicks "Pay $0.05" before each action. Pre-funded credits or monthly subscription wrapping pay-per-call underneath is mandatory.

4. **Category** — `career` must exist in the taxonomy before Koach can list or buy anything. Done above.

5. **Local fallback** — When marketplace is unreachable, Koach must fall back to local templates (it already has this via `ProfileAiGenerator` and `ProfileEvaluatorFallback`). Marketplace is an upgrade, not a dependency.
