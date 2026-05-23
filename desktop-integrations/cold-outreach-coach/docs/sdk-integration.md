# SDK Integration

This document provides concrete Dart code for integrating the **Cold Outreach Coach** with the **AI Market Protocol v2** via the `aimarket_agent` Dart SDK.

The SDK lives at `../../aimarket-sdks/dart/` in this monorepo and is imported as a path dependency:

```yaml
# pubspec.yaml
dependencies:
  aimarket_agent:
    path: ../../aimarket-sdks/dart
```

---

## 1. Initialization

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

/// Create a marketplace agent.
///
/// [hubUrl] points to the marketplace hub (or a federated hub).
/// [walletKey] is the user's EVM private key (hex-encoded, no 0x prefix).
///     In production, this comes from the OS keychain, never from code.
final AimarketAgent agent = AimarketAgent(
  hubUrl: 'https://hub.aicom.io',
  walletKey: walletKey,  // from flutter_secure_storage / keychain
  affiliate: 'cold-outreach-coach-v1',
);

// Optional: trust specific code hashes for TEE verification
agent.trustCodeHash(
  'deliverability-rules-2026-q2',
  'sha256:a1b2c3d4e5f6...',
);
agent.trustCodeHash(
  'content-heuristics-2026',
  'sha256:f6e5d4c3b2a1...',
);
```

---

## 2. Discovery (Phase 1)

```dart
/// Discover capabilities matching a natural-language intent.
///
/// Returns ranked [PlanStep] objects, each wrapping a [Capability].
Future<List<PlanStep>> discoverDeliverabilityRules() async {
  final plan = await agent.discover(
    intent: 'email deliverability rules for cold outreach Q2 2026',
    budget: 5.00,
    category: 'career',
    limit: 10,
  );

  for (final step in plan) {
    print('${step.capability.name} '
        '(\$${step.capability.pricePerCallUsd}/call, '
        'relevance: ${step.relevanceScore.toStringAsFixed(2)})');
    print('  ${step.capability.description}');
    print('  TEE verified: ${step.capability.trustScore}');
  }

  return plan;
}
```

**Direct product lookup** (when you know the product ID):

```dart
final plan = await agent.discoverProduct('deliverability-rules-2026-q2');
```

---

## 3. Open Channel (Phase 2)

```dart
/// Open a pre-funded payment channel.
///
/// [depositUsd] is the amount to deposit. A $5 channel covers ~50 checks
/// at typical $0.10/call pricing.
///
/// Returns a [Channel] with the channel ID, balance, and expiry.
Future<Channel> openPaymentChannel({double depositUsd = 5.00}) async {
  final channel = await agent.openChannel(
    depositUsd,
    token: 'USDT',
    chain: 'base',
  );

  print('Channel opened: ${channel.id}');
  print('Balance: \$${channel.balanceUsd}');
  print('Expires: ${channel.expiresAt}');

  return channel;
}
```

---

## 4. Invoke (Phase 3)

### Full integration example

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

/// Full cold-outreach check: discover → channel → invoke → settle.
Future<void> checkEmailDeliverability({
  required String walletKey,
  required String industry,
  required String targetRole,
  required int wordCount,
  required int paragraphCount,
  required bool hasQuestions,
  required int linkCount,
}) async {
  // ── Init agent ────────────────────────────────────────────────
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  try {
    // ── Phase 1: Discover ───────────────────────────────────────
    print('🔍 Discovering deliverability rules...');
    final plan = await agent.discover(
      intent: 'email deliverability rules for cold outreach Q2 2026',
      category: 'career',
    );

    if (plan.isEmpty) {
      print('No capabilities found for this intent.');
      return;
    }

    // Pick the highest-relevance capability
    final bestStep = plan.first;
    print('Selected: ${bestStep.capability.name} '
        '(relevance: ${bestStep.relevanceScore})');

    // ── Phase 2: Open channel ───────────────────────────────────
    print('💰 Opening payment channel...');
    final channel = await agent.openChannel(5.00);
    print('Channel: ${channel.id} (balance: \$${channel.balanceUsd})');

    // ── Phase 3: Invoke ─────────────────────────────────────────
    print('🚀 Invoking capability...');
    final result = await agent.invoke(
      capabilityId: bestStep.capability.id,
      input: {
        'industry': industry,
        'target_role': targetRole,
        'word_count': wordCount,
        'paragraph_count': paragraphCount,
        'has_questions': hasQuestions,
        'link_count': linkCount,
      },
      channelId: channel.id,
      verifyTee: true,
    );

    if (!result.success) {
      if (result.safetyBlocked) {
        print('⛔ Safety blocked: ${result.safetyReason}');
      } else {
        print('❌ Invocation failed: ${result.error}');
      }
      return;
    }

    print('✅ Result: ${result.output}');
    print('💵 Cost: \$${result.priceUsd}');
    print('⏱ Latency: ${result.latencyMs.toStringAsFixed(0)}ms');
    print('🔒 TEE verified: ${result.teeVerified}');

    // ── Phase 4: Settle ─────────────────────────────────────────
    print('🧾 Settling channel...');
    final settlement = await agent.closeChannel(channel.id);
    print('Refund: \$${settlement.refundUsd}');
    print('Total spent: \$${settlement.totalSpentUsd}');
    print('Invocations: ${settlement.invocations}');

  } finally {
    agent.dispose();
  }
}
```

---

## 5. TEE Verification (Phase 5)

### Pre-invoke verification

```dart
/// Before sending data to an untrusted capability, verify its TEE attestation.
///
/// This ensures the capability runs the expected code in a known enclave.
bool verifyCapabilityBeforeUse(AimarketAgent agent, PlanStep step) {
  // In a real integration, the manifest is fetched alongside the capability.
  // For illustration, we construct one from the capability metadata.
  final attestation = TeeAttestation(
    platform: 'aws_nitro',
    enclaveId: 'eni-abc123',
    codeHash: 'sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6',
    pcrValues: {'pcr0': 'expected_pcr0_value'},
    instanceId: 'i-0abcd1234efgh5678',
    region: 'us-east-1',
    timestamp: DateTime.now().toUtc().toIso8601String(),
    ttlS: 300,
    signature: 'pending',  // verified by hub
  );

  final verified = agent.verifyTeeAttestation(
    attestation,
    step.capability.id,
  );

  if (!verified) {
    print('WARNING: TEE attestation verification failed for '
        '${step.capability.name}');
    return false;
  }

  print('TEE attestation valid for ${step.capability.name}');
  return true;
}
```

### Post-invoke receipt verification

```dart
/// After receiving a result, verify the TEE receipt.
///
/// This proves the output was generated inside the attested enclave
/// using the exact input you sent.
bool verifyExecutionReceipt(
  AimarketAgent agent,
  InvokeResult result,
  String sentInput,
  String receivedOutput,
) {
  if (result.teeReceipt == null) {
    print('No TEE receipt provided — execution may not be verifiable');
    return false;
  }

  final valid = agent.verifyTeeReceipt(
    result.teeReceipt!,
    sentInput,
    receivedOutput,
  );

  if (!valid) {
    print('TEE receipt verification FAILED — output may have been tampered');
    return false;
  }

  print('TEE receipt valid — output was generated in attested enclave');
  return true;
}
```

---

## 6. Full 5-Phase Convenience Method

```dart
/// Run the complete marketplace cycle for a single cold-email check.
///
/// This uses [AimarketAgent.runOnce] which internally does:
///   1. discover  2. openChannel  3. invoke  4. closeChannel  5. BOM
Future<BillOfMaterials> checkDeliverabilityOneShot({
  required String walletKey,
  required String industry,
  required String targetRole,
  required int wordCount,
  required int paragraphCount,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  try {
    final bom = await agent.runOnce(
      intent: 'deliverability check for cold email $industry $targetRole',
      input: {
        'industry': industry,
        'target_role': targetRole,
        'word_count': wordCount,
        'paragraph_count': paragraphCount,
      },
      depositUsd: 5.00,
      category: 'career',
    );

    print('Task: ${bom.task}');
    print('Total spent: \$${bom.totalSpentUsd}');
    print('Results: ${bom.results.length}');
    print('Settlement refund: \$${bom.settlement?.refundUsd}');

    return bom;
  } finally {
    agent.dispose();
  }
}
```

---

## 7. Service-Level Integration

For production use, wrap the agent in a dedicated service class:

```dart
/// Production service for marketplace interactions.
///
/// Manages the agent lifecycle, channel caching, and error recovery.
class MarketplaceService {
  AimarketAgent? _agent;
  Channel? _activeChannel;
  String? _walletKey;

  /// Initialize with a stored wallet key.
  Future<void> initialize(String walletKey) async {
    _walletKey = walletKey;
    _agent = AimarketAgent(
      hubUrl: 'https://hub.aicom.io',
      walletKey: walletKey,
      affiliate: 'cold-outreach-coach-v1',
    );

    // Fetch well-known to verify hub connectivity
    await _agent!.wellKnown;
    print('Marketplace service initialized');
  }

  /// Ensure an active channel exists, opening one if needed.
  Future<Channel> ensureChannel({double minBalance = 1.0}) async {
    if (_activeChannel != null && _activeChannel!.balanceUsd >= minBalance) {
      return _activeChannel!;
    }

    // Close old channel if depleted
    if (_activeChannel != null) {
      try {
        await _agent!.closeChannel(_activeChannel!.id);
      } catch (_) {}
      _activeChannel = null;
    }

    _activeChannel = await _agent!.openChannel(5.00);
    return _activeChannel!;
  }

  /// Check a cold email's deliverability.
  Future<DeliverabilityReport> checkDeliverability({
    required String industry,
    required String targetRole,
    required int wordCount,
    required int paragraphCount,
    required bool hasQuestions,
    required int linkCount,
  }) async {
    if (_agent == null) throw StateError('Call initialize() first');

    // 1. Discover best capability
    final plan = await _agent!.discover(
      intent: 'deliverability rules for cold outreach $industry $targetRole',
      category: 'career',
    );
    if (plan.isEmpty) throw Exception('No deliverability rules found');

    // 2. Ensure channel
    final channel = await ensureChannel();

    // 3. Invoke
    final result = await _agent!.invoke(
      capabilityId: plan.first.capability.id,
      input: {
        'industry': industry,
        'target_role': targetRole,
        'word_count': wordCount,
        'paragraph_count': paragraphCount,
        'has_questions': hasQuestions,
        'link_count': linkCount,
      },
      channelId: channel.id,
    );

    if (!result.success) {
      throw Exception('Check failed: ${result.error ?? result.safetyReason}');
    }

    return DeliverabilityReport.fromJson(result.output!);
  }

  /// Settle and dispose.
  Future<void> dispose() async {
    if (_activeChannel != null) {
      try {
        await _agent!.closeChannel(_activeChannel!.id);
      } catch (_) {}
    }
    _agent?.dispose();
    _agent = null;
  }
}

/// Structured deliverability report.
class DeliverabilityReport {
  final double score;
  final List<String> warnings;
  final List<String> recommendations;

  const DeliverabilityReport({
    required this.score,
    required this.warnings,
    required this.recommendations,
  });

  factory DeliverabilityReport.fromJson(Map<String, dynamic> json) {
    return DeliverabilityReport(
      score: (json['deliverability_score'] as num?)?.toDouble() ?? 0,
      warnings: List<String>.from(json['warnings'] as List? ?? []),
      recommendations: List<String>.from(json['recommendations'] as List? ?? []),
    );
  }
}
```

---

## 8. Error Handling Reference

| Error | HTTP Code | Meaning | Recovery |
|-------|-----------|---------|----------|
| `AimarketException: Discovery failed` | 4xx/5xx | Hub unreachable or query failed | Retry with different intent; check hub URL |
| `AimarketException: Payment channels not available` | 404 | Hub doesn't support channels | Use a different hub or runOnce() which handles it |
| `AimarketException: Payment required` | 402 | Channel depleted | Open a new channel with larger deposit |
| `InvokeResult.safetyBlocked == true` | 403 | Input triggered safety gate | Review input fields; remove any PII |
| `InvokeResult.teeVerified == false` | 200 | TEE not verified | Check attestation; verify receipt manually |

---

## 9. Testing with the SDK

```dart
import 'package:test/test.dart';
import 'package:aimarket_agent/aimarket_agent.dart';
import 'package:cold_outreach_coach/services/marketplace_service.dart';

void main() {
  group('MarketplaceService', () {
    late MarketplaceService service;

    setUp(() {
      service = MarketplaceService();
    });

    test('initializes from wallet key', () async {
      // In CI, this would be mocked. Here we test the contract.
      await expectLater(
        () => service.initialize('test-dev-key'),
        returnsNormally,
      );
    });

    test('DeliverabilityReport parses from JSON', () {
      final report = DeliverabilityReport.fromJson({
        'deliverability_score': 85,
        'warnings': ['Link density high'],
        'recommendations': ['Reduce to 2 links'],
      });

      expect(report.score, 85);
      expect(report.warnings, contains('Link density high'));
      expect(report.recommendations.length, 1);
    });
  });

  group('Structural metrics (local only)', () {
    test('word count is correct', () {
      const text = 'Hi Alex — quick question about your cold outreach.';
      expect(text.split(RegExp(r'\s+')).length, 8);
    });

    test('paragraph count is correct', () {
      const text = 'Para one.\n\nPara two.\n\nPara three.';
      expect(text.split(RegExp(r'\n\s*\n')).length, 3);
    });

    test('question count is correct', () {
      const text = 'Interested? Let me know! Free this week?';
      expect('?'.allMatches(text).length, 2);
    });

    test('link count is correct', () {
      const text = 'Check https://example.com and http://test.com';
      expect(RegExp(r'https?://').allMatches(text).length, 2);
    });
  });
}
```

---

## 10. SDK API Reference

For the complete SDK reference, see the [aimarket_agent Dart SDK source](../../aimarket-sdks/dart/lib/):

| File | Contents |
|------|----------|
| `aimarket_agent.dart` | Library exports |
| `src/agent.dart` | `AimarketAgent` class — 5-phase cycle |
| `src/models.dart` | Data models: `Capability`, `Channel`, `InvokeResult`, `PlanStep`, `Settlement`, `BillOfMaterials`, `TeeAttestation`, `TeeReceipt` |
| `src/signer.dart` | `MarketSigner` — Ed25519 message signing |
| `src/tee_verifier.dart` | `TeeVerifier` — TEE attestation and receipt verification |
