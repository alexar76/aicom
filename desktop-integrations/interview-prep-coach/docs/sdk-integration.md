# SDK Integration

This document provides concrete Dart code examples for integrating Interview Prep Coach with the `aimarket_agent` SDK.

---

## Setup

### pubspec.yaml Dependency

```yaml
dependencies:
  aimarket_agent:
    path: ../aimarket-sdks/dart
```

Or from GitHub:

```yaml
dependencies:
  aimarket_agent:
    git:
      url: https://github.com/alexar76/aimarket-sdks.git
      path: dart
```

### Import

```dart
import 'package:aimarket_agent/aimarket_agent.dart';
```

---

## 1. Discovery: Finding Interview Capabilities

### Basic Discovery

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

void main() async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: 'your-wallet-private-key-hex',
  );

  // Discover Google SWE behavioral question banks
  final plan = await agent.discover(
    intent: 'Google SWE behavioral questions',
    budget: 5.00,
    category: 'career',
  );

  for (final step in plan) {
    print('Capability: ${step.capability.name}');
    print('  ID: ${step.capability.id}');
    print('  Price: \$${step.capability.pricePerCallUsd}');
    print('  Trust Score: ${step.capability.trustScore}');
    print('  Relevance: ${step.relevanceScore}');
    print('  Rationale: ${step.rationale}');
  }

  agent.dispose();
}
```

### Discovery with Company/Role Tags

The marketplace supports structured tags. Use them in your intent query:

```dart
// Discovery for a specific company and role
Future<List<PlanStep>> discoverForTarget({
  required String company,
  required String role,
  double budget = 5.00,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  final plan = await agent.discover(
    intent: '$company $role interview questions 2026'
        ' tagged company:${company.toLowerCase()} role:${role.toLowerCase()}',
    budget: budget,
    category: 'career',
  );

  agent.dispose();
  return plan;
}

// Usage
final results = await discoverForTarget(
  company: 'Google',
  role: 'Software Engineer',
);
```

### Discovery of Real-Time Signals

```dart
Future<List<PlanStep>> discoverRecentSignals({
  required String company,
  String? role,
  double budget = 2.00,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  // The intent includes temporal qualifiers to get fresh signals
  final intent = StringBuffer('recent interview questions asked at $company');
  if (role != null) intent.write(' for $role');
  intent.write(' "what was asked this week" after:2026-05-01');

  final signals = await agent.discover(
    intent: intent.toString(),
    budget: budget,
    category: 'career',
    limit: 20,
  );

  agent.dispose();
  return signals;
}
```

### Direct Product Lookup

If you already know the product ID, you can look it up directly:

```dart
Future<PlanStep?> findProduct(String productId) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  final plan = await agent.discoverProduct(productId);
  agent.dispose();

  if (plan.isEmpty) return null;
  return plan.first;
}

// Usage
final product = await findProduct('google-swe-q3-2026');
```

### Discovery Response Shape

Each `PlanStep` returned by discovery contains:

```dart
class PlanStep {
  final Capability capability;
  final double relevanceScore;  // 0.0 to 1.0
  final String rationale;       // Why this capability matches your intent
}

class Capability {
  final String id;               // e.g., "google-swe-q3-2026"
  final String productId;        // e.g., "google-swe-q3-2026"
  final String name;             // e.g., "Google SWE Q3 2026 Question Bank"
  final String version;          // e.g., "2.1.0"
  final String description;      // Human-readable description
  final Map<String, dynamic>? inputSchema;   // JSON Schema for input
  final Map<String, dynamic>? outputSchema;  // JSON Schema for output
  final double pricePerCallUsd;  // e.g., 0.10
  final double? p50LatencyMs;    // Median latency
  final double? successRate30d;  // 30-day success rate
  final String sourceHub;        // Federated hub URL
  final String? sourceHubName;   // Human-readable hub name
  final double? trustScore;      // 0.0 to 1.0
}
```

---

## 2. Opening a Payment Channel

### Open Channel with Default Token

```dart
final channel = await agent.openChannel(5.00);
print('Channel ID: ${channel.id}');
print('Deposit: \$${channel.depositUsd}');
print('Balance: \$${channel.balanceUsd}');
print('Token: ${channel.token}');
print('Chain: ${channel.chain}');
print('Expires: ${channel.expiresAt}');
```

### Open Channel with Specific Token and Chain

```dart
// Open on Base with USDC instead of default USDT
final channel = await agent.openChannel(
  10.00,
  token: 'USDC',
  chain: 'base',
);
```

### Channel Response Shape

```dart
class Channel {
  final String id;           // Channel identifier
  final double depositUsd;   // Amount deposited
  final double balanceUsd;   // Remaining balance
  final String token;        // e.g., "USDT", "USDC"
  final String chain;        // e.g., "base", "arbitrum", "polygon"
  final DateTime expiresAt;  // Channel expiration
}
```

### Checking and Replenishing

```dart
// Check if we have enough balance
if (channel.balanceUsd < 1.00) {
  // Close and reopen with more funds
  await agent.closeChannel(channel.id);
  channel = await agent.openChannel(10.00);
}
```

---

## 3. Invoking a Capability

### Basic Invocation

```dart
final result = await agent.invoke(
  capabilityId: 'google-swe-q3-2026',
  input: {
    'target_role': 'Software Engineer',
    'years_experience': 4,
    'focus_areas': ['leadership', 'conflict_resolution'],
    'difficulty': 'medium',
    'count': 10,
  },
  channelId: channel.id,
  verifyTee: true,
);

print('Success: ${result.success}');
print('Output: ${result.output}');
print('Price: \$${result.priceUsd}');
print('Latency: ${result.latencyMs}ms');
print('TEE verified: ${result.teeVerified}');
```

### Invocation with Federated Hub Routing

If the capability is hosted on a different hub, route explicitly:

```dart
final result = await agent.invoke(
  capabilityId: 'google-swe-q3-2026',
  input: input,
  channelId: channel.id,
  sourceHub: 'https://hub-seller.aicom.io',
  productId: 'google-swe-q3-2026',
);
```

### Handling Safety Blocks

The marketplace has safety gates that can block harmful requests:

```dart
final result = await agent.invoke(
  capabilityId: 'google-swe-q3-2026',
  input: input,
  channelId: channel.id,
);

if (result.safetyBlocked) {
  print('Request blocked: ${result.safetyReason}');
  // Adjust input and retry
} else if (!result.success) {
  print('Invocation failed: ${result.error}');
} else {
  print('Questions received: ${result.output}');
}
```

### Handling Payment Errors

```dart
try {
  final result = await agent.invoke(
    capabilityId: 'google-swe-q3-2026',
    input: input,
    channelId: channel.id,
  );
} on AimarketException catch (e) {
  if (e.message.contains('depleted')) {
    print('Channel depleted. Opening a new channel...');
    final newChannel = await agent.openChannel(5.00);
    // Retry with new channel
  } else {
    print('Marketplace error: $e');
  }
}
```

### Invocation Result Shape

```dart
class InvokeResult {
  final bool success;
  final Map<String, dynamic>? output;    // The capability output (questions, etc.)
  final double priceUsd;                  // Cost of this call
  final double latencyMs;                 // Execution time
  final bool safetyBlocked;               // Blocked by safety gate?
  final String? safetyReason;             // Why it was blocked
  final bool teeVerified;                 // TEE attestation verified?
  final TeeAttestation? teeAttestation;    // Attestation document
  final TeeReceipt? teeReceipt;            // Execution receipt
  final String? error;                     // Error message if failed
}
```

### Interview Question Invocation (Full Example)

```dart
Future<List<Map<String, dynamic>>> getInterviewQuestions({
  required String capabilityId,
  required String targetRole,
  required int yearsExperience,
  required List<String> focusAreas,
  String difficulty = 'medium',
  int count = 10,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  // 1. Open channel
  final channel = await agent.openChannel(5.00);

  // 2. Invoke
  final result = await agent.invoke(
    capabilityId: capabilityId,
    input: {
      'target_role': targetRole,
      'years_experience': yearsExperience,
      'focus_areas': focusAreas,
      'difficulty': difficulty,
      'count': count,
    },
    channelId: channel.id,
    verifyTee: true,
  );

  if (!result.success) {
    await agent.closeChannel(channel.id);
    agent.dispose();
    throw Exception('Invocation failed: ${result.error}');
  }

  // 3. Parse questions from output
  final questions = (result.output?['questions'] as List<dynamic>?)
          ?.cast<Map<String, dynamic>>() ??
      [];

  // 4. Don't close yet — user may ask more questions

  return questions;
}
```

---

## 4. Channel Settlement

### Close Channel with Refund

```dart
final settlement = await agent.closeChannel(channel.id);

print('Channel: ${settlement.channelId}');
print('Total spent: \$${settlement.totalSpentUsd}');
print('Refunded: \$${settlement.refundUsd}');
print('Invocations: ${settlement.invocations}');
```

### Settlement Response Shape

```dart
class Settlement {
  final String channelId;
  final double totalSpentUsd;   // Total amount spent
  final double refundUsd;        // Refund to wallet
  final int invocations;         // Number of capability calls
}
```

---

## 5. TEE Attestation Verification

### Pre-Invocation Attestation Check

Before sending data to a capability, verify it runs in a TEE:

```dart
// First, get the attestation from the capability manifest
// (In production, fetched as part of discovery or via a manifest endpoint)
final TeeAttestation attestation = capability.teeAttestation; // fetched separately

// Register the expected code hash
agent.trustCodeHash(
  'google-swe-q3-2026',
  'sha256:a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b',
);

// Verify before sending
final isVerified = agent.verifyTeeAttestation(
  attestation,
  'google-swe-q3-2026',
);

if (!isVerified) {
  print('WARNING: TEE attestation verification FAILED.');
  print('The capability may not be running in a secure enclave.');
  // Optionally abort the invocation
  return;
}

print('TEE attestation verified:');
print('  Platform: ${attestation.platform}');
print('  Enclave ID: ${attestation.enclaveId}');
print('  Code hash: ${attestation.codeHash}');
print('  Region: ${attestation.region}');
print('  Not expired: ${!attestation.isExpired}');
```

### Post-Invocation Receipt Verification

After receiving output, verify it was produced in the TEE:

```dart
final result = await agent.invoke(
  capabilityId: 'google-swe-q3-2026',
  input: input,
  channelId: channel.id,
);

if (result.teeReceipt != null) {
  final inputJson = json.encode(input);
  final outputJson = json.encode(result.output);

  final receiptVerified = agent.verifyTeeReceipt(
    result.teeReceipt!,
    inputJson,
    outputJson,
  );

  if (!receiptVerified) {
    print('WARNING: TEE receipt verification FAILED!');
    print('The output may not have been produced in the attested enclave.');
  } else {
    print('TEE receipt verified. Output was produced in secure enclave.');
    print('  Receipt ID: ${result.teeReceipt!.receiptId}');
    print('  Input hash: ${result.teeReceipt!.inputHash}');
    print('  Output hash: ${result.teeReceipt!.outputHash}');
  }
}
```

### Full Trust Verification Chain

```dart
Future<bool> fullTrustVerification({
  required AimarketAgent agent,
  required TeeAttestation attestation,
  required String capabilityId,
  required Map<String, dynamic> input,
  required String channelId,
}) async {
  // Phase 1: Pre-check attestation
  final attVerified = agent.verifyTeeAttestation(attestation, capabilityId);
  if (!attVerified) {
    print('Phase 1 FAILED: Attestation not valid');
    return false;
  }
  print('Phase 1 PASSED: Attestation valid');

  // Phase 2: Invoke
  final result = await agent.invoke(
    capabilityId: capabilityId,
    input: input,
    channelId: channelId,
    verifyTee: false, // Already verified
  );

  if (!result.success) {
    print('Phase 2 FAILED: Invocation failed');
    return false;
  }
  print('Phase 2 PASSED: Invocation successful');

  // Phase 3: Post-check receipt
  if (result.teeReceipt == null) {
    print('Phase 3 FAILED: No TEE receipt returned');
    return false;
  }

  final receiptVerified = agent.verifyTeeReceipt(
    result.teeReceipt!,
    json.encode(input),
    json.encode(result.output),
  );

  if (!receiptVerified) {
    print('Phase 3 FAILED: Receipt not valid');
    return false;
  }
  print('Phase 3 PASSED: Receipt valid');

  print('Full trust chain VERIFIED');
  return true;
}
```

---

## 6. Full Bill of Materials (BOM) Example

The `runOnce` method runs the full 5-phase cycle and returns a BOM:

```dart
Future<BillOfMaterials> prepareForInterview({
  required String company,
  required String role,
  required List<String> focusAreas,
}) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  final intent = '$company $role behavioral questions on ${focusAreas.join(', ')}';
  final input = {
    'target_role': role,
    'years_experience': 6,
    'focus_areas': focusAreas,
    'difficulty': 'hard',
    'count': 15,
  };

  try {
    final bom = await agent.runOnce(
      intent: intent,
      input: input,
      depositUsd: 10.00,
      category: 'career',
    );

    print('=== BILL OF MATERIALS ===');
    print('Task: ${bom.task}');
    print('Protocol: ${bom.protocolVersion}');
    print('Total spent: \$${bom.totalSpentUsd}');

    print('\n--- Discovery Plan ---');
    for (final step in bom.plan) {
      print('  ${step.capability.name} (relevance: ${step.relevanceScore})');
      print('    Price: \$${step.capability.pricePerCallUsd}/call');
      print('    Trust: ${step.capability.trustScore}');
    }

    print('\n--- Invocation Results ---');
    for (final result in bom.results) {
      if (result.success) {
        final questions = (result.output?['questions'] as List?) ?? [];
        print('  Got ${questions.length} questions');
        print('  Cost: \$${result.priceUsd}');
        print('  Latency: ${result.latencyMs}ms');
        print('  TEE verified: ${result.teeVerified}');
      } else {
        print('  FAILED: ${result.error}');
      }
    }

    if (bom.settlement != null) {
      print('\n--- Settlement ---');
      print('  Spent: \$${bom.settlement!.totalSpentUsd}');
      print('  Refunded: \$${bom.settlement!.refundUsd}');
      print('  Invocations: ${bom.settlement!.invocations}');
    }

    return bom;
  } catch (e) {
    print('Marketplace error: $e');
    rethrow;
  } finally {
    agent.dispose();
  }
}
```

Expected output:

```
=== BILL OF MATERIALS ===
Task: Google Software Engineer behavioral questions on leadership, conflict resolution
Protocol: v2
Total spent: $1.50

--- Discovery Plan ---
  Google SWE Q3 2026 Question Bank (relevance: 0.94)
    Price: $0.10/call
    Trust: 0.95
  Google Behavioral Patterns 2026 (relevance: 0.88)
    Price: $0.15/call
    Trust: 0.92

--- Invocation Results ---
  Got 15 questions
  Cost: $0.10
  Latency: 230ms
  TEE verified: true

--- Settlement ---
  Spent: $0.10
  Refunded: $4.90
  Invocations: 1
```

---

## 7. Complete Service Integration

Here is the complete `MarketplaceService` class used by Interview Prep Coach:

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

class MarketplaceService {
  final AimarketAgent _agent;
  Channel? _activeChannel;

  MarketplaceService({
    required String hubUrl,
    required String walletKey,
    Map<String, String>? trustedCodeHashes,
  }) : _agent = AimarketAgent(
          hubUrl: hubUrl,
          walletKey: walletKey,
          trustedCodeHashes: trustedCodeHashes ?? {
            'google-swe-q3-2026': 'sha256:a1b2c3d4e5f6...',
            'google-behavioral-2026': 'sha256:b2c3d4e5f6a7...',
            'amazon-leadership-2026': 'sha256:c3d4e5f6a7b8...',
            'meta-behavioral-2026': 'sha256:d4e5f6a7b8c9...',
          },
        );

  // ── Discover ────────────────────────────────────────────

  Future<List<PlanStep>> discoverInterviewQuestions({
    required String company,
    required String role,
    String? focusArea,
    double budget = 5.00,
  }) {
    final intent = StringBuffer('$company $role interview');
    if (focusArea != null) intent.write(' $focusArea');
    intent.write(
      ' tagged company:${company.toLowerCase()} role:${role.toLowerCase()}',
    );
    return _agent.discover(intent: intent.toString(), budget: budget, category: 'career');
  }

  Future<List<PlanStep>> discoverRecentSignals({
    required String company,
    String? role,
    double budget = 2.00,
  }) {
    final intent = StringBuffer('recent $company interview');
    if (role != null) intent.write(' $role');
    intent.write(' "what was asked this week" after:2026-05-01');
    return _agent.discover(intent: intent.toString(), budget: budget, category: 'career');
  }

  // ── Channel ─────────────────────────────────────────────

  Future<Channel> ensureChannel({double depositUsd = 5.00}) async {
    if (_activeChannel != null && _activeChannel!.balanceUsd > 0.50) {
      return _activeChannel!;
    }
    if (_activeChannel != null) {
      await _agent.closeChannel(_activeChannel!.id);
    }
    _activeChannel = await _agent.openChannel(depositUsd);
    return _activeChannel!;
  }

  // ── Invoke ──────────────────────────────────────────────

  Future<InvokeResult> getInterviewQuestions({
    required String capabilityId,
    required Map<String, dynamic> input,
    String? productId,
  }) async {
    final channel = await ensureChannel();
    return _agent.invoke(
      capabilityId: capabilityId,
      input: input,
      channelId: channel.id,
      productId: productId,
      verifyTee: true,
    );
  }

  Future<InvokeResult> submitAnonymizedTrajectory({
    required Map<String, dynamic> trajectory,
    required String capabilityId,
  }) async {
    final sanitized = _stripPii(trajectory);
    final channel = await ensureChannel();
    return _agent.invoke(
      capabilityId: capabilityId,
      input: sanitized,
      channelId: channel.id,
    );
  }

  // ── Settle ──────────────────────────────────────────────

  Future<Settlement?> closeChannel() async {
    if (_activeChannel == null) return null;
    final settlement = await _agent.closeChannel(_activeChannel!.id);
    _activeChannel = null;
    return settlement;
  }

  // ── Verify ──────────────────────────────────────────────

  bool verifyAttestation(TeeAttestation attestation, String capabilityId) {
    return _agent.verifyTeeAttestation(attestation, capabilityId);
  }

  bool verifyReceipt(TeeReceipt receipt, String input, String output) {
    return _agent.verifyTeeReceipt(receipt, input, output);
  }

  // ── Privacy ─────────────────────────────────────────────

  Map<String, dynamic> _stripPii(Map<String, dynamic> data) {
    final sanitized = Map<String, dynamic>.from(data);
    sanitized.remove('candidate_name');
    sanitized.remove('email');
    sanitized.remove('phone');
    sanitized.remove('linkedin_url');
    sanitized.remove('resume_text');
    sanitized.remove('interviewer_name');

    if (sanitized.containsKey('company')) {
      // Hash company name to one-way identifier
      sanitized['company_hash'] = _hashField(sanitized['company'].toString());
      sanitized.remove('company');
    }
    return sanitized;
  }

  // ── Lifecycle ───────────────────────────────────────────

  void dispose() => _agent.dispose();
}
```

---

## 8. Best Practices

### Channel Management

- **Open channels with sufficient deposit** for your expected usage. A $5 channel covers ~50 calls at $0.10 each.
- **Check balance before invoking**. If balance drops below a threshold, close and reopen.
- **Always close channels** when done. Unused balance is refunded.

### TEE Verification

- **Always verify attestations** before sending personal data (e.g., company names, experience details).
- **Always verify receipts** after receiving outputs that influence decisions (e.g., question quality).
- **Register trusted code hashes** for frequently-used capabilities.

### Error Handling

- **Handle 402 (Payment Required)**: Channel depleted. Open a new channel and retry.
- **Handle 403 (Safety Blocked)**: Adjust input to comply with safety policies.
- **Handle timeouts**: Retry with exponential backoff (max 3 retries).

### Privacy

- **Strip PII client-side** before invoking any capability. Do not rely on the hub or seller to do this.
- **Use TEE-verified capabilities** for sensitive queries (e.g., company-specific questions).
- **Encrypt local data** (wallet keys, practice history) using platform keychains.
