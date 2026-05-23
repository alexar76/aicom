# SDK Integration

The Freelance Contract Reviewer uses the `aimarket_agent` Dart SDK to interact with the AI Market Protocol v2 marketplace. This document shows the key integration points with code examples.

---

## Setup

In `pubspec.yaml`:

```yaml
dependencies:
  aimarket_agent:
    path: ../../aimarket-sdks/dart
```

Import:

```dart
import 'package:aimarket_agent/aimarket_agent.dart';
```

---

## 1. Initialize the agent

```dart
final agent = AimarketAgent(
  hubUrl: 'https://hub.aicom.io',
  walletKey: walletPrivateKey,       // from flutter_secure_storage
  // Trusted code hashes for known clause libraries
  trustedCodeHashes: {
    'cap_ca_ip_clauses_v2': 'abc123def456...',
    'cap_ny_noncompete_2026': '7890abcd...',
  },
);
```

---

## 2. Search for clause libraries

```dart
/// Returns a list of PlanSteps matching the intent
Future<List<PlanStep>> searchClauseLibraries(String jurisdiction) async {
  final results = await agent.discover(
    intent: '$jurisdiction freelance contract clause library',
    budget: 10.00,
    category: 'legal',
    limit: 10,
  );

  for (final step in results) {
    print('${step.capability.name} — \$${step.capability.pricePerCallUsd}');
    print('  ${step.capability.description}');
    print('  Trust score: ${step.capability.trustScore}');
    print('  TEE: ${step.capability.sourceHub}');
  }

  return results;
}
```

---

## 3. Purchase and evaluate a clause library (full cycle)

```dart
/// Purchase a clause library and evaluate extracted clauses against it.
Future<InvokeResult> checkClauses({
  required String capabilityId,
  required List<Map<String, dynamic>> anonymizedClauses,
  required String libraryName,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  // Step 1: Open a $5 payment channel
  final channel = await agent.openChannel(5.00);

  // Step 2: Verify TEE attestation before sending data
  // (In practice, fetch the manifest, then verify.)
  final manifestVerified = agent.verifyTeeAttestation(
    attestation,   // from manifest
    capabilityId,
  );
  if (!manifestVerified) {
    throw Exception('TEE attestation failed — cannot trust enclave');
  }

  // Step 3: Invoke the clause library
  final result = await agent.invoke(
    capabilityId: capabilityId,
    input: {
      'library_name': libraryName,
      'clauses': anonymizedClauses,
      'review_mode': 'full',
      'include_suggestions': true,
    },
    channelId: channel.id,
  );

  // Step 4: Verify TEE receipt
  if (result.teeReceipt != null) {
    final receiptValid = agent.verifyTeeReceipt(
      result.teeReceipt!,
      jsonEncode(anonymizedClauses),
      jsonEncode(result.output),
    );
    if (!receiptValid) {
      print('WARNING: TEE receipt verification failed!');
    }
  }

  // Step 5: Settle channel
  final settlement = await agent.closeChannel(channel.id);
  print('Spent: \$${settlement.totalSpentUsd} | Refund: \$${settlement.refundUsd}');

  agent.dispose();
  return result;
}
```

---

## 4. Run the full 5-phase cycle (convenience)

```dart
/// One-shot: discover + open channel + invoke + settle + return BOM.
Future<BillOfMaterials> evaluateContract({
  required String jurisdiction,
  required List<Map<String, dynamic>> anonymizedClauses,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  try {
    return await agent.runOnce(
      intent: '$jurisdiction freelance contract clause library for devs',
      input: {
        'clauses': anonymizedClauses,
        'mode': 'quick_check',
      },
      depositUsd: 5.00,
      category: 'legal',
    );
  } finally {
    agent.dispose();
  }
}

// Usage:
final bom = await evaluateContract(
  jurisdiction: 'California',
  anonymizedClauses: anonymizedClauses,
);
print('Total spent: \$${bom.totalSpentUsd}');
print('Results: ${bom.results.length} clauses evaluated');
```

---

## 5. Sell anonymized dispute patterns

```dart
/// Submit an anonymized clause pattern to the marketplace.
/// Returns the InvokeResult with the marketplace listing info.
Future<InvokeResult> sellDisputePattern({
  required Map<String, dynamic> anonymizedPattern,
  required String channelId,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  // Use the marketplace's "submit pattern" capability
  final result = await agent.invoke(
    capabilityId: 'cap_marketplace_submit_pattern_v2',
    input: {
      'pattern_type': 'dispute_clause',
      'clause_shape': anonymizedPattern,
      'category': 'dispute_pattern',
      'royalty_per_resale_usd': 0.15,
    },
    channelId: channelId,
  );

  agent.dispose();
  return result;
}
```

---

## 6. Handling errors

```dart
try {
  final result = await agent.invoke(...);
  if (result.safetyBlocked) {
    print('Safety gate blocked: ${result.safetyReason}');
    // e.g., "Clause mentions prohibited category: gambling"
    return;
  }
  if (!result.success) {
    print('Invocation failed: ${result.error}');
    return;
  }
  // Process output
} on AimarketException catch (e) {
  if (e.message.contains('channel depleted')) {
    // Open a new channel with larger deposit
    await agent.openChannel(10.00);
    // Retry...
  }
  print('Marketplace error: $e');
} finally {
  agent.dispose();
}
```

---

## 7. Trusted code hash verification (security best practice)

```dart
// During app startup, pin known-good code hashes for trusted publishers.
agent.trustCodeHash('cap_ip_clause_ca_v2', 'sha256:abc123...');
agent.trustCodeHash('cap_noncompete_ny_2026', 'sha256:def456...');

// Before each invoke, verify the current attestation matches.
// This prevents supply-chain attacks where a hub swaps capabilities.
final verified = agent.verifyTeeAttestation(
  currentAttestation,
  capabilityId,
);
if (!verified) {
  // DO NOT SEND DATA — the enclave is not running the expected code.
  throw Exception('Code hash mismatch — possible tampering');
}
```

---

## Marketplace capability schema (for reference)

### Standard clause library input

```json
{
  "library_name": "California IP Clauses for Freelancers v2",
  "clauses": [
    {
      "type": "ip_ownership",
      "text": "All work product shall be the exclusive property of Client..."
    },
    {
      "type": "payment_terms",
      "text": "Net-30 from date of invoice..."
    }
  ],
  "review_mode": "full",
  "include_suggestions": true
}
```

### Standard clause library output

```json
{
  "clause_results": [
    {
      "type": "ip_ownership",
      "risk": "high",
      "matched_rules": [
        {
          "rule_id": "CA_IP_OVERRBROAD_001",
          "rule_name": "Overbroad assignment without license-back",
          "severity": "high",
          "citation": "Cal. Civ. Code § 3426",
          "explanation": "Assignment without license-back is unusual in..."
        }
      ],
      "suggestion": "Add: 'Designer retains a perpetual, royalty-free license...'",
      "confidence": 0.94
    }
  ],
  "overall_risk": "high",
  "total_issues": 1,
  "library_version": "2.1.0",
  "evaluated_in_tee": true
}
```

### Anonymized pattern sell input

```json
{
  "pattern_type": "dispute_clause",
  "clause_shape": {
    "type": "ip_ownership",
    "jurisdiction": "CA",
    "risk": "high",
    "clause_structure": "overbroad_assignment_no_license_back",
    "dispute_outcome": "client_demanded_full_ownership",
    "was_disputed": true,
    "industry": "software_development",
    "party_types": ["freelance_developer", "startup_client"]
  },
  "category": "dispute_pattern",
  "royalty_per_resale_usd": 0.15
}
```
