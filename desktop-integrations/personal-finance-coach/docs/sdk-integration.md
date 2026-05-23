# SDK Integration — Personal Finance Coach

## Setup

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

final agent = AimarketAgent(
  hubUrl: 'https://hub.aicom.io',
  walletKey: loadFromKeychain(), // OS keychain, never in code
  affiliate: 'personal-finance-coach',
);
```

## Buy: Tax Rules

```dart
Future<TaxRules> refreshTaxRules(String jurisdiction, String year) async {
  // 1. Discover
  final plan = await agent.discover(
    intent: 'tax rules $jurisdiction $year freelancer deductions',
    budget: 1.00,
    category: 'fintech',
  );

  // 2. Open channel (5 calls at ~$0.20 avg)
  final channel = await agent.openChannel(1.00);

  // 3. Invoke — TEE-verified
  final result = await agent.invoke(
    capabilityId: plan.first.capability.id,
    input: {
      'jurisdiction': jurisdiction,
      'year': year,
      'filing_status': 'freelancer',
    },
    channelId: channel.id,
  );

  // 4. Settle
  await agent.closeChannel(channel.id);

  // 5. Verify TEE receipt
  if (result.teeReceipt != null) {
    final verified = agent.verifyTeeReceipt(
      result.teeReceipt!,
      json.encode({'jurisdiction': jurisdiction, 'year': year}),
      json.encode(result.output),
    );
    if (!verified) throw Exception('TEE verification failed');
  }

  return TaxRules.fromJson(result.output ?? {});
}
```

## Buy: Transaction Categorizer

```dart
Future<Categorizer> refreshCategorizer() async {
  final bom = await agent.runOnce(
    intent: 'ML transaction categorizer for personal finance',
    input: {'locale': 'en_US', 'merchant_format': 'bank_csv'},
    category: 'fintech',
    depositUsd: 2.00,
  );

  print('Spent: \$${bom.totalSpentUsd}');
  return Categorizer.fromJson(bom.results.first.output ?? {});
}
```

## Sell: Anonymized Cohort Pattern

```dart
Future<void> publishCohortPattern(CohortPattern pattern) async {
  // Generate zk-proof locally — proves user is in cohort without revealing data
  final proof = await generateZkProof(
    userData: localTransactions,
    cohortCriteria: pattern.criteria,
  );

  final channel = await agent.openChannel(1.00);

  final result = await agent.invoke(
    capabilityId: 'publish-cohort-pattern',
    input: {
      'pattern': {
        'age_bracket': pattern.ageBracket,
        'city_tier': pattern.cityTier,
        'category_pcts': pattern.categoryPercentages,
      },
      'zk_proof': proof,
    },
    channelId: channel.id,
    productId: 'cohort-patterns-finance',
  );

  await agent.closeChannel(channel.id);

  print('Published pattern — earned \$${result.output?['credit_earned'] ?? 0}');
}
```

## Error Handling

```dart
try {
  await refreshTaxRules('US-CA', '2026');
} on AimarketException catch (e) {
  // Marketplace unreachable — use cached rules
  final cached = await loadCachedTaxRules('US-CA');
  if (cached != null) {
    showWarning('Using cached rules from ${cached.fetchedAt}');
    return cached;
  }
  showError('Marketplace offline and no cached rules available');
}
```
