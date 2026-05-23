# Architecture

## Overview

Discovery Prospector is a Flutter desktop application that implements a **demand-supply gap detection pipeline** over the AI Market hub's aggregated telemetry. It is both a standalone GUI tool and a programmatic SDK consumer/producer.

```
┌─────────────────────────────────────────────────────┐
│                  Discovery Prospector                 │
│                                                       │
│  ┌──────────┐   ┌────────────┐   ┌────────────────┐ │
│  │ Telemetry │──▶│   Gap      │──▶│   Insight       │ │
│  │ Collector │   │  Detector   │   │   Publisher     │ │
│  └──────────┘   └────────────┘   └────────────────┘ │
│         │                │                  │          │
│         ▼                ▼                  ▼          │
│  ┌─────────────────────────────────────────────┐      │
│  │         aimarket_agent SDK (Dart)            │      │
│  └─────────────────────────────────────────────┘      │
│         │                                              │
└─────────┼──────────────────────────────────────────────┘
          │
          ▼
  ┌────────────────┐
  │  AI Market Hub │
  │  (hub.aicom.io)│
  └────────────────┘
```

---

## Telemetry Aggregation

### Data Sources

Discovery Prospector consumes two telemetry capabilities from the hub:

| Capability | Returns | Frequency |
|---|---|---|
| `marketplace-telemetry-aggregated` | Aggregated search volume, purchase attempts, and supply counts per category/sub-category | Daily aggregated |
| `marketplace-search-trends` | Trending search terms and category velocity over configurable windows | Near-real-time |

### Collection Pipeline

1. **Pull**: On startup and user refresh, the app invokes `marketplace-telemetry-aggregated` with optional category and period filters.
2. **Cache**: Raw telemetry is cached locally in a SQLite database (via `sqflite_common_ffi`) for offline browsing and delta computation.
3. **Normalize**: Category names, sub-category paths, and search terms are normalized against the marketplace taxonomy.
4. **Index**: Each data point is indexed by `(category, sub_category, period)` for fast query.

```dart
class TelemetryCollector {
  final AimarketAgent agent;
  final Database cache;

  Future<List<TelemetrySnapshot>> pullTelemetry({
    String? category,
    String period = '30d',
  }) async {
    final result = await agent.invoke(
      capabilityId: 'marketplace-telemetry-aggregated',
      input: {'category': category, 'period': period},
      channelId: channel.id,
    );
    final snapshots = (result.output?['snapshots'] as List)
        .map((s) => TelemetrySnapshot.fromJson(s))
        .toList();
    await cacheTelemetry(snapshots);
    return snapshots;
  }
}
```

---

## Gap Detection Algorithm

### Core Insight

A **gap** exists when:
```
demand(term) >> supply(term)
```

Where:
- `demand(term)` = number of unique searches for `term` in period + number of purchase attempts that returned zero results
- `supply(term)` = count of published capabilities that match `term`

### Algorithm Pseudocode

```
for each (category, sub_category) in telemetry:
    search_volume      = telemetry.search_count(category, sub_category)
    purchase_attempts  = telemetry.purchase_attempts(category, sub_category)
    supply_count       = telemetry.supply_count(category, sub_category)
    
    demand_score = normalize(search_volume + purchase_attempts, 0, MAX_DEMAND)
    supply_score = 1 - normalize(supply_count, 0, MAX_SUPPLY)
    
    gap_score = demand_score * supply_score  // demand with no supply = high gap
    
    if gap_score > GAP_THRESHOLD:
        emit GapInsight(
            category: category,
            subCategory: sub_category,
            demandScore: demand_score,
            supplyCount: supply_count,
            gapScore: gap_score,
            estimatedMarketUsd: estimate_market(search_volume, purchase_attempts),
            suggestedCapabilityType: suggest_type(category, sub_category),
        )
```

### Scoring Parameters

| Parameter | Default | Description |
|---|---|---|
| `MAX_DEMAND` | 10,000 | Maximum expected search + purchase volume for normalization |
| `MAX_SUPPLY` | 50 | Maximum expected capability count per sub-category |
| `GAP_THRESHOLD` | 0.6 | Minimum gap score to emit an insight |
| `LOOKBACK_PERIOD` | 30d | Default telemetry window |

### Normalization

Demand and supply are normalized using min-max scaling clamped to [0, 1]:

```
normalized(x, min, max) = clamp((x - min) / (max - min), 0, 1)
```

### Edge Cases

1. **Zero telemetry**: If a category has no telemetry data, it is excluded (insufficient signal).
2. **New categories**: Categories with zero supply but non-zero demand are treated as maximum gaps.
3. **Seasonal spikes**: Telemetry uses a rolling 30-day window to smooth daily variance.
4. **Spam protection**: Categories with abnormally high search-to-purchase ratios are flagged and down-weighted.

---

## Underserved Niche Scoring

Each detected gap receives a composite score used for ranking:

```
niche_score = 0.40 * demand_score
            + 0.30 * supply_scarcity
            + 0.15 * estimated_market_score
            + 0.10 * growth_velocity
            + 0.05 * builder_ecosystem_fit
```

### Score Components

| Component | Weight | Description |
|---|---|---|
| `demand_score` | 0.40 | Normalized search + purchase volume |
| `supply_scarcity` | 0.30 | Inverse of capability count in this niche |
| `estimated_market_score` | 0.15 | Projected monthly revenue potential (normalized) |
| `growth_velocity` | 0.10 | Week-over-week change in search volume |
| `builder_ecosystem_fit` | 0.05 | How well the niche aligns with existing builder tooling |

### Insight Output Format

```json
{
  "insight_id": "gap-c6f8a2e1",
  "niche": "ATS rules for Greenhouse",
  "category": "career",
  "sub_category": "ats-scoring",
  "demand_score": 0.87,
  "supply_count": 0,
  "supply_scarcity": 1.0,
  "estimated_monthly_searches": 342,
  "estimated_monthly_purchase_attempts": 89,
  "average_price_willing_to_pay_usd": 0.15,
  "estimated_monthly_market_usd": 4104,
  "growth_velocity": 0.12,
  "builder_ecosystem_fit": 0.73,
  "niche_score": 0.81,
  "suggested_capability_type": "scoring-function",
  "example_input_schema": {
    "type": "object",
    "properties": {
      "candidate_profile": {"type": "string"},
      "job_description": {"type": "string"},
      "ats_system": {"type": "string", "enum": ["greenhouse", "lever", "workday"]}
    }
  },
  "created_at": "2025-05-23T00:00:00Z"
}
```

---

## Marketplace SDK Integration

Discovery Prospector participates in the marketplace in two directions:

### Buying (Telemetry Input)

The app is a **consumer** of hub telemetry capabilities. It pays per-invocation to pull aggregated data. This creates a revenue stream for hub operators and telemetry providers.

### Selling (Insight Output)

The app is a **producer** of `publish-gap-insight` capability. When a third-party developer buys this insight, it is a marketplace transaction paid through the standard channel mechanism.

### SDK Dependency

In `pubspec.yaml`:

```yaml
dependencies:
  aimarket_agent:
    path: ../aimarket-sdks/dart
```

The `aimarket_agent` package provides the full protocol cycle: discovery, channel management, invocation with payment, and TEE verification.

---

## Data Flow Diagram

```
                    ┌──────────────────┐
                    │  Hub Telemetry   │
                    │  Provider        │
                    └────────┬─────────┘
                             │ marketplace-telemetry-aggregated
                             ▼
              ┌──────────────────────────┐
              │  TelemetryCollector      │
              │  - pulls raw telemetry   │
              │  - caches in SQLite      │
              │  - normalizes categories │
              └────────────┬─────────────┘
                           │ normalized telemetry
                           ▼
              ┌──────────────────────────┐
              │  GapDetector             │
              │  - scores demand/supply  │
              │  - detects underserved   │
              │  - ranks by niche_score  │
              └────────────┬─────────────┘
                           │ gap insights
                           ▼
              ┌──────────────────────────┐
              │  InsightPublisher        │
              │  - serves via dashboard  │
              │  - sells via SDK invoke  │
              └──────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
     ┌─────────────────┐    ┌────────────────────┐
     │  Desktop GUI     │    │  SDK Consumer      │
     │  (Flutter app)   │    │  (publish-gap-     │
     │                  │    │   insight invoke)  │
     └─────────────────┘    └────────────────────┘
```

---

## Security Considerations

- **Telemetry is aggregated only.** No individual user search histories are exposed — only counts and normalized scores.
- **Wallet keys** are stored in the platform keychain (not in plaintext).
- **TEE verification** ensures published gap insights were computed inside a trusted enclave, providing integrity guarantees to buyers.
- **Rate limiting** prevents bulk scraping of gap insights.
