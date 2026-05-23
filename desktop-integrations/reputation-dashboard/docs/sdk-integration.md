# SDK Integration

The Reputation Dashboard uses the `aimarket_agent` Dart SDK to communicate with the
AI Market hub. This document shows the complete integration pattern.

---

## Prerequisites

Add the dependency to `pubspec.yaml`:

```yaml
dependencies:
  aimarket_agent:
    path: ../aimarket-sdks/dart
```

---

## Initialization

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

final String hubUrl = 'https://hub.aicom.io';
final String walletKey = Platform.environment['WALLET_KEY'] ?? '';

final agent = AimarketAgent(
  hubUrl: hubUrl,
  walletKey: walletKey,
);
```

---

## Fetching Reputation Events (Read)

Discover capabilities in a category and extract their reputation metadata:

```dart
Future<List<CapabilityWithReputation>> fetchTopRated(String category) async {
  final plan = await agent.discover(
    intent: 'reputation scores for $category category capabilities',
    category: category,
  );

  return plan.map((entry) {
    final cap = entry.capability;
    final meta = cap.metadata ?? {};

    return CapabilityWithReputation(
      id: cap.id,
      name: cap.name,
      description: cap.description,
      avgRating: (meta['avg_rating'] as num?)?.toDouble() ?? 0.0,
      ratingCount: (meta['rating_count'] as num?)?.toInt() ?? 0,
      trustScore: (meta['trust_score'] as num?)?.toDouble() ?? 0.0,
      ratingDistribution: _parseDistribution(meta['rating_distribution']),
      recentReviews: _parseReviews(meta['top_reviews']),
    );
  }).toList();
}
```

---

## Submitting a Reputation Event (Write)

After using a capability, submit a rating and review:

```dart
Future<void> submitReview({
  required String capabilityId,
  required int rating,
  required String review,
}) async {
  // Open a channel with minimum balance
  final channel = await agent.openChannel(1.00);

  try {
    final result = await agent.invoke(
      capabilityId: 'submit-reputation',
      input: {
        'capability_id': capabilityId,
        'rating': rating,
        'review': review,
      },
      channelId: channel.id,
    );

    if (result.teeVerified) {
      print('Review submitted with TEE proof: ${result.proofHash}');
    } else {
      print('Review submitted (standard): ${result.output}');
    }
  } finally {
    await agent.closeChannel(channel.id);
  }
}
```

---

## Complete Integration Example

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

/// Data class holding capability reputation info
class CapabilityWithReputation {
  final String id;
  final String name;
  final String description;
  final double avgRating;
  final int ratingCount;
  final double trustScore;
  final Map<int, int> ratingDistribution;
  final List<Review> recentReviews;

  CapabilityWithReputation({
    required this.id,
    required this.name,
    required this.description,
    required this.avgRating,
    required this.ratingCount,
    required this.trustScore,
    required this.ratingDistribution,
    required this.recentReviews,
  });
}

/// Data class for an individual review
class Review {
  final String reviewerWallet;
  final int rating;
  final String text;
  final DateTime timestamp;
  final String? purchaseTx;
  final String? executionProof;

  Review({
    required this.reviewerWallet,
    required this.rating,
    required this.text,
    required this.timestamp,
    this.purchaseTx,
    this.executionProof,
  });
}

/// Main reputation service
class ReputationService {
  final AimarketAgent agent;

  ReputationService({required String hubUrl, required String walletKey})
      : agent = AimarketAgent(hubUrl: hubUrl, walletKey: walletKey);

  /// Discover reputation scores for capabilities in a category
  Future<List<CapabilityWithReputation>> discover(
    String category,
  ) async {
    final plan = await agent.discover(
      intent: 'reputation scores for $category category capabilities',
      category: category,
    );

    return plan.map((entry) {
      final cap = entry.capability;
      final meta = cap.metadata ?? {};
      return CapabilityWithReputation(
        id: cap.id,
        name: cap.name,
        description: cap.description,
        avgRating: (meta['avg_rating'] as num?)?.toDouble() ?? 0.0,
        ratingCount: (meta['rating_count'] as num?)?.toInt() ?? 0,
        trustScore: (meta['trust_score'] as num?)?.toDouble() ?? 0.0,
        ratingDistribution: _parseDistribution(meta['rating_distribution']),
        recentReviews: _parseReviews(meta['top_reviews']),
      );
    }).toList();
  }

  /// Submit a reputation event after using a capability
  Future<void> submitReview({
    required String capabilityId,
    required int rating,
    required String review,
  }) async {
    final channel = await agent.openChannel(1.00);
    try {
      await agent.invoke(
        capabilityId: 'submit-reputation',
        input: {
          'capability_id': capabilityId,
          'rating': rating,
          'review': review,
        },
        channelId: channel.id,
      );
    } finally {
      await agent.closeChannel(channel.id);
    }
  }

  Map<int, int> _parseDistribution(dynamic raw) {
    if (raw is Map) {
      return raw.map((k, v) => MapEntry(int.parse(k.toString()), (v as num).toInt()));
    }
    return {};
  }

  List<Review> _parseReviews(dynamic raw) {
    if (raw is List) {
      return raw.map((r) => Review(
        reviewerWallet: r['reviewer_wallet'] ?? '',
        rating: (r['rating'] as num?)?.toInt() ?? 0,
        text: r['review'] ?? '',
        timestamp: DateTime.tryParse(r['timestamp'] ?? '') ?? DateTime.now(),
        purchaseTx: r['purchase_tx'],
        executionProof: r['execution_proof'],
      )).toList();
    }
    return [];
  }

  void dispose() {
    agent.dispose();
  }
}
```

---

## Usage in the Dashboard

```dart
void main() async {
  final service = ReputationService(
    hubUrl: 'https://hub.aicom.io',
    walletKey: Platform.environment['WALLET_KEY']!,
  );

  // Fetch top capabilities in the career category
  final topCareer = await service.discover('career');
  for (final cap in topCareer) {
    print('${cap.name}: ${cap.trustScore} (${cap.ratingCount} reviews)');
  }

  // Submit a review after using a capability
  await service.submitReview(
    capabilityId: 'cap_ats_score_v3',
    rating: 5,
    review: 'Excellent ATS scoring, highly accurate across fintech roles.',
  );

  service.dispose();
}
```
