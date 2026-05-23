# Architecture

## Overview

The Reputation Dashboard is a Flutter desktop application that reads reputation data from
the AI Market hub and presents it in interactive visualizations. It both **consumes**
reputation events (read) and **submits** them (write) through the same `AimarketAgent` SDK.

```
┌──────────────────────────────────────────────────┐
│              Reputation Dashboard                │
│  ┌────────────────────────────────────────────┐  │
│  │         Flutter UI (Desktop)               │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐   │  │
│  │  │ Buyer    │ │ Seller   │ │ Curator  │   │  │
│  │  │ View     │ │ View     │ │ Console  │   │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘   │  │
│  │       │             │            │         │  │
│  │  ┌────▼─────────────▼────────────▼─────┐   │  │
│  │  │       Reputation Service Layer       │   │  │
│  │  │  (fetch / aggregate / submit)        │   │  │
│  │  └────────────────┬─────────────────────┘   │  │
│  └───────────────────┼─────────────────────────┘  │
│                      │                            │
│              ┌───────▼────────┐                   │
│              │ AimarketAgent  │                   │
│              │   (SDK)        │                   │
│              └───────┬────────┘                   │
└──────────────────────┼───────────────────────────┘
                       │ HTTPS / WebSocket
              ┌────────▼────────┐
              │   hub.aicom.io  │
              │  ┌──────────┐   │
              │  │reputation│   │
              │  │  plugin  │   │
              │  └──────────┘   │
              └─────────────────┘
```

---

## Reputation Data Flow

### 1. Event Emission (Write Path)

When a buyer completes a purchase and uses a capability, they submit a reputation event:

```
User Action
    │
    ▼
Dashboard UI (Review Form)
    │
    ▼
AimarketAgent.invoke(capabilityId: "submit-reputation", input: {...})
    │
    ▼
hub.aicom.io → reputation plugin → on-chain event
```

The reputation plugin records:
- `capability_id` — the capability being rated
- `rating` — integer score (1-5)
- `review` — free-text review
- `reviewer_wallet` — derived from the signing wallet key
- `purchase_tx` — link to the purchase transaction (proves the reviewer actually bought it)
- `timestamp` — block timestamp

### 2. Event Reading (Read Path)

```
Dashboard Launch
    │
    ▼
AimarketAgent.discover(intent: "reputation scores for ...", category: "...")
    │
    ▼
hub.aicom.io → reputation plugin → query index
    │
    ▼
Dashboard aggregates and renders
```

The SDK returns a `Plan` containing capabilities whose metadata includes reputation
aggregates. The dashboard extracts the aggregate scores and renders them.

### 3. Aggregation Pipeline

Raw events are aggregated by the reputation plugin into:

| Aggregate | Description |
|---|---|
| `avg_rating` | Mean of all ratings (1-5 scale) |
| `rating_count` | Total number of ratings |
| `rating_distribution` | Histogram of 1-5 star counts |
| `trust_score` | Weighted score: avg_rating * min(rating_count / threshold, 1) |
| `recent_trend` | Slope of ratings over the last 30 days |
| `top_reviews` | Most helpful recent reviews |

---

## Trust Score Visualization

The trust score is the primary metric shown in the dashboard. It is computed as:

```
trust_score = avg_rating * min(rating_count / MIN_REVIEWS_THRESHOLD, 1)
```

This means:
- Capabilities with fewer than `MIN_REVIEWS_THRESHOLD` reviews have their score dampened
- Once the threshold is crossed, the score equals the average rating
- A capability with 5.0 avg but only 1 review scores lower than one with 4.5 and 20 reviews

### Visual Encoding

| Trust Score | Color | Meaning |
|---|---|---|
| 4.0 - 5.0 | Green / #22c55e | Highly trusted |
| 3.0 - 3.9 | Amber / #f59e0b | Moderate trust |
| 1.0 - 2.9 | Red / #ef4444 | Low trust |
| No data | Gray / #6b7280 | Not yet rated |

---

## Marketplace SDK Integration

The dashboard implements the `AimarketAgent` pattern in two modes:

### Read Mode (Discovery)

```dart
final agent = AimarketAgent(hubUrl: hubUrl, walletKey: walletKey);
final plan = await agent.discover(
  intent: 'reputation scores for career category capabilities',
  category: 'career',
);
```

The resulting `Plan` contains capabilities with embedded reputation metadata. The
dashboard parses `capability.metadata['reputation']` to extract aggregates.

### Write Mode (Submission)

```dart
await agent.invoke(
  capabilityId: 'submit-reputation',
  input: {
    'capability_id': ratedCapabilityId,
    'rating': 5,
    'review': 'Excellent ATS scoring, highly accurate across fintech roles.',
  },
  channelId: channel.id,
);
```

See [sdk-integration.md](sdk-integration.md) for full code examples.

---

## State Management

The dashboard uses a lightweight reactive pattern:

- **ReputationRepository** — fetches and caches reputation data from the hub
- **AggregateService** — computes trust scores, distributions, trends
- **ViewModels** — Flutter `ChangeNotifier` models per screen
- **Widgets** — Pure presentation, rebuild on ViewModel changes

No external state management library is required — the app is small enough that
`provider` or `ChangeNotifier` suffices.

---

## Security & Trust

1. **Signed requests** — Every API call is signed with the user's wallet key
2. **TEE verification** — Capability execution can be TEE-verified via the SDK's
   `teeVerifier`; reputation events from TEE-executed capabilities carry an
   `execution_proof` field
3. **Purchase proof** — Reviews are linked to on-chain purchase transactions,
   preventing review fraud
