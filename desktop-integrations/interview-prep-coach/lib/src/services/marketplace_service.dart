/// Wraps the aimarket_agent SDK for interview-specific marketplace operations.
///
/// Provides high-level methods for discovering interview capabilities,
/// opening payment channels, invoking question banks, and verifying
/// TEE attestations — all scoped to the interview preparation domain.
library;

import 'dart:convert';

import 'package:aimarket_agent/aimarket_agent.dart';
import 'package:crypto/crypto.dart';

/// Manages marketplace interactions for interview prep.
///
/// Uses the [AimarketAgent] under the hood to implement the full
/// 5-phase lifecycle: Discover -> Channel -> Invoke -> Settle -> Verify.
class MarketplaceService {
  final AimarketAgent _agent;
  Channel? _activeChannel;

  MarketplaceService({required String hubUrl, String? walletKey})
      : _agent = AimarketAgent(
          hubUrl: hubUrl,
          walletKey: walletKey ?? '',
          trustedCodeHashes: {
            'google-swe-q3-2026': 'sha256:a1b2c3d4e5f6...',
            'meta-behavioral-2026': 'sha256:f6e5d4c3b2a1...',
            'amazon-leadership-2026': 'sha256:9a8b7c6d5e4f...',
          },
        );

  /// Discover interview question banks for a specific company and role.
  ///
  /// Example intent: "Google SWE behavioral questions 2026"
  Future<List<PlanStep>> discoverInterviewQuestions({
    required String company,
    required String role,
    String? focusArea,
    double budget = 5.00,
  }) async {
    final intent = StringBuffer('$company $role interview questions');
    if (focusArea != null) intent.write(' $focusArea');
    intent.write(
      ' tagged company:$company role:$role',
    );

    return _agent.discover(
      intent: intent.toString(),
      budget: budget,
      category: 'career',
      limit: 10,
    );
  }

  /// Discover real-time "what was asked this week" signals.
  ///
  /// These are anonymized, fresh question reports from recent interviews.
  Future<List<PlanStep>> discoverRecentSignals({
    required String company,
    String? role,
    double budget = 2.00,
  }) async {
    final intent = StringBuffer('recent interview questions asked at $company');
    if (role != null) intent.write(' for $role');
    intent.write(' "what was asked this week" after:2026-05-01');

    return _agent.discover(
      intent: intent.toString(),
      budget: budget,
      category: 'career',
      limit: 20,
    );
  }

  /// Open a payment channel for interview prep purchases.
  ///
  /// A $5 channel covers approximately 50 question bank invocations at $0.10 each.
  Future<Channel> ensureChannel({double depositUsd = 5.00}) async {
    if (_activeChannel != null) {
      // Check if existing channel has sufficient balance.
      if (_activeChannel!.balanceUsd > 0.50) return _activeChannel!;
      // Close depleted channel.
      await _agent.closeChannel(_activeChannel!.id);
    }
    _activeChannel = await _agent.openChannel(depositUsd);
    return _activeChannel!;
  }

  /// Invoke a question bank to get personalized interview questions.
  ///
  /// [capabilityId] from discovery, e.g. "google-swe-q3-2026".
  /// [input] includes target role, years of experience, specific topics.
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

  /// Submit an anonymized interview trajectory to the marketplace.
  ///
  /// This is the sell side: users can share "question -> answer -> offer/reject"
  /// to earn credits. All PII is stripped client-side before submission.
  Future<InvokeResult> submitAnonymizedTrajectory({
    required Map<String, dynamic> trajectory,
    required String capabilityId,
  }) async {
    // Strip PII before sending.
    final sanitized = _stripPii(trajectory);
    final channel = await ensureChannel();
    return _agent.invoke(
      capabilityId: capabilityId,
      input: sanitized,
      channelId: channel.id,
    );
  }

  /// Verify TEE attestation for a capability.
  bool verifyAttestation(TeeAttestation attestation, String capabilityId) {
    return _agent.verifyTeeAttestation(attestation, capabilityId);
  }

  /// Verify TEE receipt after invocation.
  bool verifyReceipt(TeeReceipt receipt, String input, String output) {
    return _agent.verifyTeeReceipt(receipt, input, output);
  }

  /// Get the current channel balance.
  double? get channelBalance => _activeChannel?.balanceUsd;

  /// Close the active channel and get refund.
  Future<Settlement?> closeChannel() async {
    if (_activeChannel == null) return null;
    final settlement = await _agent.closeChannel(_activeChannel!.id);
    _activeChannel = null;
    return settlement;
  }

  /// Run a full 5-phase cycle for a single interview prep query.
  Future<BillOfMaterials> runOnce({
    required String intent,
    required Map<String, dynamic> input,
    double depositUsd = 5.00,
  }) async {
    return _agent.runOnce(
      intent: intent,
      input: input,
      depositUsd: depositUsd,
      category: 'career',
    );
  }

  /// Strip personally identifiable information from a trajectory before
  /// submitting to the marketplace. Runs entirely on-device.
  Map<String, dynamic> _stripPii(Map<String, dynamic> data) {
    final sanitized = Map<String, dynamic>.from(data);
    // Remove direct PII fields.
    sanitized.remove('candidate_name');
    sanitized.remove('email');
    sanitized.remove('phone');
    sanitized.remove('linkedin_url');
    sanitized.remove('resume_text');

    // Hash company-level identifiers.
    if (sanitized.containsKey('company')) {
      sanitized['company_hash'] = _hashField(sanitized['company'].toString());
      sanitized.remove('company');
    }
    if (sanitized.containsKey('interviewer_name')) {
      sanitized.remove('interviewer_name');
    }
    if (sanitized.containsKey('location')) {
      sanitized['location_region'] = _regionFromLocation(
        sanitized['location'].toString(),
      );
      sanitized.remove('location');
    }

    return sanitized;
  }

  String _hashField(String value) {
    final bytes = utf8.encode(value);
    return sha256.convert(bytes).toString().substring(0, 16);
  }

  String _regionFromLocation(String location) {
    // Map specific locations to broad regions.
    const regionMap = {
      'San Francisco': 'US-West',
      'New York': 'US-East',
      'Seattle': 'US-West',
      'London': 'EU-West',
      'Berlin': 'EU-Central',
      'Bangalore': 'APAC-South',
    };
    return regionMap.entries
        .firstWhere(
          (e) => location.contains(e.key),
          orElse: () => const MapEntry('', 'Other'),
        )
        .value;
  }

  void dispose() {
    _agent.dispose();
  }
}
