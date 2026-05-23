# SDK Integration: Creator Algorithm Coach + aimarket_agent

This document shows real Dart code patterns for buying algorithm signals and selling verified performance data using the `aimarket_agent` SDK.

## Prerequisites

Add to `pubspec.yaml`:

```yaml
dependencies:
  aimarket_agent:
    path: ../../aimarket-sdks/dart
```

## Initialization

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

final agent = AimarketAgent(
  hubUrl: 'https://hub.aicom.io',
  walletKey: walletPrivateKeyHex,
  affiliate: 'creator-algorithm-coach',
);

// Optional: register known-good code hashes for trusted sellers
agent.trustCodeHash(
  'tiktok-optimal-times-cooking-v3',
  'sha256:a1b2c3d4e5f6...',
);
agent.trustCodeHash(
  'youtube-algorithm-shift-detector-v2',
  'sha256:f6e5d4c3b2a1...',
);
```

## Use Case: Buy Algorithm Signals for TikTok Cooking Niche

```dart
Future<void> buyTikTokCookingSignals() async {
  // ── 1. DISCOVER what's available ─────────────────────────────
  print('Searching for TikTok cooking algorithm signals...');
  final plan = await agent.discover(
    intent: 'algorithm signals for tiktok cooking niche - '
            'optimal posting times, trend windows, hook structures',
    budget: 5.00,
    category: 'creator',
    limit: 10,
  );

  if (plan.isEmpty) {
    print('No capabilities found for this niche.');
    return;
  }

  // Show results
  for (final step in plan) {
    print('  [${step.relevanceScore.toStringAsFixed(2)}] '
        '${step.capability.name} — '
        '\$${step.capability.pricePerCallUsd.toStringAsFixed(2)}/call');
    print('    ${step.rationale}');
  }

  // ── 2. OPEN CHANNEL ──────────────────────────────────────────
  print('\nOpening \$5 payment channel...');
  final channel = await agent.openChannel(5.00);
  print('Channel opened: ${channel.id}');
  print('Balance: \$${channel.balanceUsd.toStringAsFixed(2)}');

  // ── 3. INVOKE selected capability ────────────────────────────
  final bestMatch = plan.first;
  print('\nInvoking: ${bestMatch.capability.name}');

  final result = await agent.invoke(
    capabilityId: bestMatch.capability.id,
    input: {
      'platform': 'tiktok',
      'niche': 'cooking',
      'include_trend_windows': true,
      'include_hook_benchmarks': true,
    },
    channelId: channel.id,
    productId: bestMatch.capability.productId,
    sourceHub: bestMatch.capability.sourceHub,
    verifyTee: true, // verify attestation before sending data
  );

  if (!result.success) {
    if (result.safetyBlocked) {
      print('Safety blocked: ${result.safetyReason}');
    } else {
      print('Invocation failed: ${result.error}');
    }
    return;
  }

  print('Price paid: \$${result.priceUsd.toStringAsFixed(4)}');
  print('Latency: ${result.latencyMs.toStringAsFixed(0)}ms');
  print('TEE attestation (simulated): ${result.teeVerified}');

  if (result.teeVerified && result.output != null) {
    final signals = result.output!;

    print('\n=== ALGORITHM SIGNALS ===');
    print('Optimal posting time: ${signals['optimal_posting_time']}');
    print('Confidence: ${(signals['confidence'] as num?)?.toStringAsFixed(2)}');
    print('Trend window: ${signals['trend_window']}');
    print('Top hook: ${signals['top_hook']}');

    if (signals['tee_receipt'] != null) {
      print('\nTEE Receipt: ${signals['tee_receipt']}');
    }
  }

  // ── 4. SETTLE ────────────────────────────────────────────────
  print('\nClosing channel...');
  final settlement = await agent.closeChannel(channel.id);
  print('Total spent: \$${settlement.totalSpentUsd.toStringAsFixed(2)}');
  print('Refund: \$${settlement.refundUsd.toStringAsFixed(2)}');
  print('Invocations: ${settlement.invocations}');
}
```

## Use Case: Sell Verified Hook Performance Data

```dart
Future<void> sellVerifiedHookData() async {
  // ── 1. DISCOVER sell capability ──────────────────────────────
  final plan = await agent.discover(
    intent: 'publish verified creator metrics to marketplace',
    budget: 1.00,
    category: 'creator',
  );

  if (plan.isEmpty) {
    print('No publish capability available.');
    return;
  }

  // ── 2. OPEN CHANNEL (small deposit — publishing is cheap) ────
  final channel = await agent.openChannel(2.00);

  // ── 3. INVOKE with TEE attestation ───────────────────────────
  final result = await agent.invoke(
    capabilityId: plan.first.capability.id,
    channelId: channel.id,
    input: {
      'action': 'publish_metrics',
      'metrics': {
        // Metadata
        'platform': 'tiktok',
        'niche': 'cooking',
        'period_start': '2026-05-16',
        'period_end': '2026-05-22',
        'sample_size': 47,      // 47 videos analyzed

        // Performance signals
        'avg_watch_time_seconds': 23.5,
        'completion_rate': 0.34,
        'hook_ctr': 0.68,       // 68% hooked in first 3 seconds

        // Timing signals
        'optimal_posting_time': '14:14 EST',
        'secondary_window_start': '19:30 EST',
        'secondary_window_end': '21:00 EST',

        // Trend signals
        'trending_format': 'recipe_card_overlay',
        'trending_audio_category': 'upbeat_pop',
        'rising_hashtags': ['#easyrecipes', '#30minutemeals'],
      },
      'tee_attestation': true,  // Prove data was measured, not faked
      'price_per_call_usd': 0.15,
    },
    verifyTee: true,
  );

  if (result.success) {
    print('Metrics published successfully!');
    print('Listing ID: ${result.output?['listing_id']}');
    print('Price per purchase: \$${(result.output?['price_per_call_usd'] as num?)?.toStringAsFixed(2)}');
  }

  await agent.closeChannel(channel.id);
}
```

## Use Case: Full Buy Cycle with TEE Verification

```dart
Future<void> buyWithTeeVerification() async {
  // Run the full 5-phase cycle in one call
  final bom = await agent.runOnce(
    intent: 'algorithm signals for instagram reels fitness niche - '
            'optimal posting times, hook benchmarks',
    input: {
      'platform': 'instagram',
      'niche': 'fitness',
      'include_tee_proof': true,
    },
    depositUsd: 5.00,
    category: 'creator',
  );

  print('Task: ${bom.task}');
  print('Total spent: \$${bom.totalSpentUsd.toStringAsFixed(2)}');

  for (final result in bom.results) {
    print('Success: ${result.success}');
    print('TEE attestation (simulated): ${result.teeVerified}');
    print('Price: \$${result.priceUsd.toStringAsFixed(4)}');

    // Post-invoke verification
    if (result.teeReceipt != null) {
      final verified = agent.verifyTeeReceipt(
        result.teeReceipt!,
        jsonEncode(result.output),
        jsonEncode(result.output),
      );
      print('Receipt verification: ${verified ? "PASSED" : "FAILED"}');
    }
  }

  print('Refund: \$${bom.settlement?.refundUsd.toStringAsFixed(2)}');
}
```

## Running the Full Example

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

void main() async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: 'your-wallet-private-key-hex',
    affiliate: 'creator-algorithm-coach',
  );

  try {
    await buyTikTokCookingSignals();
    // await sellVerifiedHookData();
    // await buyWithTeeVerification();
  } catch (e) {
    print('Error: $e');
  } finally {
    agent.dispose();
  }
}
```

## Expected Output

```
Searching for TikTok cooking algorithm signals...
  [0.92] TikTok Optimal Posting Times — cooking — $0.15/call
    High relevance to niche: 47 creators in cooking category
  [0.87] Trend Window Detector — cooking — $0.25/call
    Rising format: recipe_card_overlay
  [0.81] Hook Structure Benchmarks — cooking — $0.20/call
    Top hook: "Stop scrolling if you love [ingredient]"

Opening $5 payment channel...
Channel opened: chan_abc123
Balance: $5.00

Invoking: TikTok Optimal Posting Times — cooking
Price paid: $0.1500
Latency: 234ms
TEE attestation (simulated): true

=== ALGORITHM SIGNALS ===
Optimal posting time: 14:14 EST
Confidence: 0.89
Trend window: recipe_card_overlay rising (velocity: +340% this week)
Top hook: "Stop scrolling if you love pasta..."

Closing channel...
Total spent: $0.15
Refund: $4.85
Invocations: 1
```
