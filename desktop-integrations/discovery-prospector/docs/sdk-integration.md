# SDK Integration

Discovery Prospector is built on the `aimarket_agent` Dart SDK. The same SDK is used to **consume** marketplace telemetry and to **publish** gap insights for external developers.

---

## Installing the SDK

In your `pubspec.yaml`, add the dependency:

```yaml
dependencies:
  aimarket_agent:
    path: ../aimarket-sdks/dart
```

For published packages (future), use:

```yaml
dependencies:
  aimarket_agent: ^0.1.0
```

---

## Initializing the Agent

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

final agent = AimarketAgent(
  hubUrl: 'https://hub.aicom.io',
  walletKey: 'your-wallet-private-key-hex',
);
```

The agent handles all protocol phases: discovery, channel management, invocation with payment, settlement, and TEE verification.

---

## Buying Marketplace Telemetry

### Aggregated Telemetry

Request search volume, purchase attempts, and supply counts for a category over a time period.

```dart
final channel = await agent.openChannel(5.00);

final telemetry = await agent.invoke(
  capabilityId: 'marketplace-telemetry-aggregated',
  input: {
    'category': 'career',
    'period': '30d',       // options: 7d, 30d, 90d
  },
  channelId: channel.id,
);

// telemetry.output contains:
// {
//   "snapshots": [
//     {
//       "category": "career",
//       "sub_category": "ats-scoring",
//       "search_count": 342,
//       "purchase_attempts": 89,
//       "supply_count": 0,
//       "avg_price_willing_to_pay_usd": 0.15
//     },
//     ...
//   ],
//   "period": "30d",
//   "generated_at": "2025-05-23T00:00:00Z"
// }

await agent.closeChannel(channel.id);
```

### Search Trends

Get trending search terms and velocity data.

```dart
final trends = await agent.invoke(
  capabilityId: 'marketplace-search-trends',
  input: {
    'window': '7d',
    'limit': 20,
  },
  channelId: channel.id,
);
```

---

## Selling Gap Insights

Once Discovery Prospector detects an underserved niche, it makes it available as a purchasable capability. External developers invoke `publish-gap-insight` to buy a specific gap insight.

```dart
final channel = await agent.openChannel(1.00); // insights are cheap

final insight = await agent.invoke(
  capabilityId: 'publish-gap-insight',
  input: {
    'niche': 'ATS rules for Greenhouse',
    'demand_score': 0.87,
    'supply_count': 0,
  },
  channelId: channel.id,
);

// insight.output contains:
// {
//   "insight_id": "gap-c6f8a2e1",
//   "niche": "ATS rules for Greenhouse",
//   "category": "career",
//   "sub_category": "ats-scoring",
//   "demand_score": 0.87,
//   "supply_count": 0,
//   "supply_scarcity": 1.0,
//   "estimated_monthly_searches": 342,
//   "estimated_monthly_purchase_attempts": 89,
//   "average_price_willing_to_pay_usd": 0.15,
//   "estimated_monthly_market_usd": 4104,
//   "growth_velocity": 0.12,
//   "niche_score": 0.81,
//   "suggested_capability_type": "scoring-function",
//   "example_input_schema": { ... }
// }

await agent.closeChannel(channel.id);
```

---

## Full Example: End-to-End Telemetry-to-Insight Pipeline

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

Future<void> main() async {
  // ── Initialize ──
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: Platform.environment['WALLET_KEY']!,
  );

  // ── Open channel for telemetry purchase ──
  final telemetryChannel = await agent.openChannel(5.00);

  // ── Pull telemetry for all priority categories ──
  final categories = ['career', 'finance', 'health', 'legal', 'education'];
  final allSnapshots = <TelemetrySnapshot>[];

  for (final cat in categories) {
    final result = await agent.invoke(
      capabilityId: 'marketplace-telemetry-aggregated',
      input: {'category': cat, 'period': '30d'},
      channelId: telemetryChannel.id,
    );

    if (result.success && result.output != null) {
      final snapshots = (result.output!['snapshots'] as List)
          .map((s) => TelemetrySnapshot.fromJson(s));
      allSnapshots.addAll(snapshots);
    }
  }

  await agent.closeChannel(telemetryChannel.id);

  // ── Detect gaps ──
  final gaps = GapDetector.detect(allSnapshots);

  // ── Open channel for insight publishing ──
  final publishChannel = await agent.openChannel(3.00);

  // ── Publish top gaps ──
  for (final gap in gaps.take(5)) {
    final result = await agent.invoke(
      capabilityId: 'publish-gap-insight',
      input: {
        'niche': gap.niche,
        'demand_score': gap.demandScore,
        'supply_count': gap.supplyCount,
        'category': gap.category,
        'sub_category': gap.subCategory,
        'estimated_monthly_searches': gap.estimatedMonthlySearches,
        'estimated_monthly_purchase_attempts': gap.estimatedMonthlyPurchaseAttempts,
        'average_price_willing_to_pay_usd': gap.avgPriceWillingToPayUsd,
        'estimated_monthly_market_usd': gap.estimatedMonthlyMarketUsd,
        'growth_velocity': gap.growthVelocity,
        'suggested_capability_type': gap.suggestedCapabilityType,
        'example_input_schema': gap.exampleInputSchema,
      },
      channelId: publishChannel.id,
    );

    if (result.success) {
      print('Published: ${gap.niche} (score: ${gap.nicheScore})');
    }
  }

  await agent.closeChannel(publishChannel.id);
  agent.dispose();
}

// ── Data structures ──

class TelemetrySnapshot {
  final String category;
  final String subCategory;
  final int searchCount;
  final int purchaseAttempts;
  final int supplyCount;
  final double avgPriceWillingToPayUsd;

  TelemetrySnapshot({
    required this.category,
    required this.subCategory,
    required this.searchCount,
    required this.purchaseAttempts,
    required this.supplyCount,
    required this.avgPriceWillingToPayUsd,
  });

  factory TelemetrySnapshot.fromJson(Map<String, dynamic> json) {
    return TelemetrySnapshot(
      category: json['category'] as String,
      subCategory: json['sub_category'] as String,
      searchCount: json['search_count'] as int,
      purchaseAttempts: json['purchase_attempts'] as int,
      supplyCount: json['supply_count'] as int,
      avgPriceWillingToPayUsd: (json['avg_price_willing_to_pay_usd'] as num).toDouble(),
    );
  }
}

class GapInsight {
  final String niche;
  final String category;
  final String subCategory;
  final double demandScore;
  final int supplyCount;
  final double nicheScore;
  final int estimatedMonthlySearches;
  final int estimatedMonthlyPurchaseAttempts;
  final double avgPriceWillingToPayUsd;
  final double estimatedMonthlyMarketUsd;
  final double growthVelocity;
  final String suggestedCapabilityType;
  final Map<String, dynamic>? exampleInputSchema;

  GapInsight({
    required this.niche,
    required this.category,
    required this.subCategory,
    required this.demandScore,
    required this.supplyCount,
    required this.nicheScore,
    required this.estimatedMonthlySearches,
    required this.estimatedMonthlyPurchaseAttempts,
    required this.avgPriceWillingToPayUsd,
    required this.estimatedMonthlyMarketUsd,
    required this.growthVelocity,
    required this.suggestedCapabilityType,
    this.exampleInputSchema,
  });
}
```

---

## Capability Reference

| Capability ID | Type | Price | Input | Output |
|---|---|---|---|---|
| `marketplace-telemetry-aggregated` | Buy | $0.10/call | `{category, period}` | Array of telemetry snapshots |
| `marketplace-search-trends` | Buy | $0.05/call | `{window, limit}` | Trending search terms with velocity |
| `publish-gap-insight` | Sell | $0.25/call | `{niche, demand_score, ...}` | Full gap insight with market estimates |

---

## Error Handling

```dart
try {
  final result = await agent.invoke(
    capabilityId: 'marketplace-telemetry-aggregated',
    input: {'category': 'career', 'period': '30d'},
    channelId: channel.id,
  );

  if (result.safetyBlocked) {
    print('Request blocked: ${result.safetyReason}');
    return;
  }

  if (!result.success) {
    print('Invocation failed: ${result.error}');
    return;
  }

  print('Telemetry received: ${result.output}');
} on AimarketException catch (e) {
  print('Protocol error: ${e.message}');
}
```

---

## TEE Verification

All returned insights include TEE attestation. To verify:

```dart
if (result.teeVerified && result.teeReceipt != null) {
  final verified = agent.verifyTeeReceipt(
    result.teeReceipt!,
    json.encode(mySentInput),
    json.encode(result.output),
  );
  print('TEE receipt verified: $verified');
}
```
