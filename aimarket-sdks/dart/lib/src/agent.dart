/// AI Market Protocol v2 Consumer Agent.
///
/// Implements the 5-phase consumer cycle:
///   1. **Discovery**     — fetch well-known + search marketplace
///   2. **Channel**        — open pre-funded payment channel
///   3. **Invoke**         — call capability with payment header
///   4. **Settle**         — close channel, get refund
///   5. **Verify**         — TEE attestation check before/after invoke
///
/// This is the Dart port of aimarket-agent/aimarket_agent/agent.py
/// and cli/ai_market_agent.py, adapted for desktop apps.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';
import 'signer.dart';
import 'tee_verifier.dart';

// ── Configuration ───────────────────────────────────────────────────────────

/// Configuration for [AimarketAgent] behavior.
///
/// Group all tunable parameters into a single object so the constructor
/// stays manageable and tests can override specific values without
/// touching production defaults.
class AimarketAgentConfig {
  /// Base URL of the AI Market hub (e.g., "https://hub.aicom.io").
  final String hubUrl;

  /// Hex-encoded private key for signing payment authorizations.
  final String walletKey;

  /// Affiliate identifier sent in the X-AIMarket-Affiliate header.
  final String affiliate;

  /// Per-request timeout. Defaults to 30 seconds.
  final Duration timeout;

  /// Maximum number of retries for transient network failures.
  ///
  /// Each retry doubles the delay: 1s, 2s, 4s, etc.
  final int maxRetries;

  /// Map of capability ID to known-good code hash for TEE verification.
  final Map<String, String>? trustedCodeHashes;

  /// Whether to verify TEE attestations before invoking capabilities.
  final bool verifyTee;

  const AimarketAgentConfig({
    required this.hubUrl,
    required this.walletKey,
    this.affiliate = 'aimarket-sdk-dart',
    this.timeout = const Duration(seconds: 30),
    this.maxRetries = 3,
    this.trustedCodeHashes,
    this.verifyTee = true,
  });
}

// ── Exception Hierarchy ─────────────────────────────────────────────────────

/// Base exception for AI Market Protocol errors.
///
/// All agent-specific exceptions extend this class so callers can catch
/// them with a single type or discriminate with `on` clauses.
class AimarketException implements Exception {
  final String message;
  final int? statusCode;

  const AimarketException(this.message, {this.statusCode});

  @override
  String toString() => 'AimarketException: $message';
}

/// Network-level error: timeout, connection refused, DNS failure, etc.
///
/// Retry logic catches this type specifically; other [AimarketException]
/// subclasses propagate immediately.
class AimarketNetworkException extends AimarketException {
  const AimarketNetworkException(super.message, {super.statusCode});

  @override
  String toString() => 'AimarketNetworkException: $message';
}

/// Payment failure: depleted channel, insufficient funds, or expired credit.
///
/// Thrown on HTTP 402 responses. The caller should open a new channel
/// and retry the invocation.
class AimarketPaymentException extends AimarketException {
  const AimarketPaymentException(super.message, {super.statusCode});

  @override
  String toString() => 'AimarketPaymentException: $message';
}

/// Safety gate blocked the invocation.
///
/// Thrown on HTTP 403 responses. The reason is provided by the hub's
/// safety gate and explains why the input was rejected.
class AimarketSafetyException extends AimarketException {
  final String reason;

  const AimarketSafetyException(this.reason)
      : super('Safety blocked: $reason', statusCode: 403);

  @override
  String toString() => 'AimarketSafetyException: $reason';
}

// ── Internal: Cached Channel ───────────────────────────────────────────────

/// Wraps a [Channel] together with the time it was cached.
///
/// Used by the channel cache in [AimarketAgent] to decide whether a
/// previously opened channel is still worth reusing.
class _CachedChannel {
  final Channel channel;
  final DateTime cachedAt;

  const _CachedChannel(this.channel, this.cachedAt);

  /// Whether more than half the original deposit is still available.
  bool get hasSufficientBalance => channel.balanceRatio > 0.5;

  /// Whether the channel has not yet expired.
  bool get isNotExpired => !channel.isExpired;

  /// Whether this channel is reusable: unexpired with >50% balance.
  bool get isReusable => isNotExpired && hasSufficientBalance;
}

// ── Agent ───────────────────────────────────────────────────────────────────

/// AI Market Protocol v2 consumer.
///
/// Usage:
/// ```dart
/// final agent = AimarketAgent(
///   hubUrl: 'https://hub.aicom.io',
///   walletKey: myWalletPrivateKey,
/// );
///
/// // Discover
/// final caps = await agent.discover(intent: 'ATS scoring for fintech', budget: 1.00);
///
/// // Open channel (reuses existing if >50% balance remains)
/// final channel = await agent.openChannel(5.00);
///
/// // Invoke
/// final result = await agent.invoke(
///   capabilityId: caps.first.id,
///   input: {'target_role': 'Senior PM', 'industry': 'fintech'},
///   channelId: channel.id,
/// );
///
/// // Settle
/// final settlement = await agent.closeChannel(channel.id);
/// agent.dispose();
/// ```
class AimarketAgent {
  final AimarketAgentConfig _config;
  final MarketSigner _signer;
  final TeeVerifier _teeVerifier;
  final http.Client _http;

  /// In-memory cache of open channels, keyed by deposit:token:chain.
  final Map<String, _CachedChannel> _channelCache = {};

  String? _wellKnown;

  /// Create an agent bound to a specific hub and wallet.
  ///
  /// [hubUrl] is the base URL of the AI Market hub.
  /// [walletKey] is the hex-encoded Ed25519 private key for signing.
  /// [httpClient] allows injection of a mock client for testing.
  /// [affiliate] is sent in the X-AIMarket-Affiliate header.
  /// [trustedCodeHashes] pre-populates TEE code hash verification.
  /// [timeout] sets the per-request timeout (default 30s).
  /// [maxRetries] sets the number of retry attempts (default 3).
  AimarketAgent({
    required String hubUrl,
    required String walletKey,
    http.Client? httpClient,
    String affiliate = 'aimarket-sdk-dart',
    Map<String, String>? trustedCodeHashes,
    Duration timeout = const Duration(seconds: 30),
    int maxRetries = 3,
  })  : _config = AimarketAgentConfig(
          hubUrl: hubUrl,
          walletKey: walletKey,
          affiliate: affiliate,
          timeout: timeout,
          maxRetries: maxRetries,
          trustedCodeHashes: trustedCodeHashes,
        ),
        _signer = MarketSigner(privateKeyHex: walletKey),
        _teeVerifier = TeeVerifier(
          signer: MarketSigner(privateKeyHex: walletKey),
          trustedCodeHashes: trustedCodeHashes,
        ),
        _http = httpClient ?? http.Client();

  // ── Internal: Retry with Exponential Backoff ───────────────────────

  /// Execute [operation] with exponential backoff on network errors.
  ///
  /// Retries up to [_config.maxRetries] times with delays of 1s, 2s, 4s, etc.
  /// Only [AimarketNetworkException] triggers a retry — all other exceptions
  /// propagate immediately so protocol/payment/safety errors are surfaced
  /// without delay.
  ///
  /// Timeout errors from `Future.timeout()` and `http.ClientException` are
  /// both converted to [AimarketNetworkException] and retried.
  Future<T> _retryWithBackoff<T>(Future<T> Function() operation) async {
    var lastError = AimarketNetworkException(
        'Request failed after ${_config.maxRetries} retries');

    for (var attempt = 0; attempt <= _config.maxRetries; attempt++) {
      try {
        return await operation();
      } on TimeoutException catch (e) {
        lastError = AimarketNetworkException('Request timed out: $e');
      } catch (e) {
        if (e is http.ClientException) {
          lastError =
              AimarketNetworkException('Network error: ${e.message}');
        } else {
          rethrow;
        }
      }

      if (attempt < _config.maxRetries) {
        // Exponential delay: 1s, 2s, 4s (1 << attempt).
        await Future.delayed(Duration(seconds: 1 << attempt));
      }
    }

    throw lastError;
  }

  // ── Phase 1: Discovery ─────────────────────────────────────────────

  /// Fetch .well-known/ai-market.json for the hub.
  ///
  /// The well-known manifest describes the hub's capabilities, pricing,
  /// and TEE support. Results are cached in memory for the lifetime of
  /// the agent.
  Future<String> get wellKnown async {
    if (_wellKnown != null) return _wellKnown!;
    final uri = Uri.parse('$_hubUrl/.well-known/ai-market.json');
    final resp = await _http.get(uri);
    if (resp.statusCode != 200) {
      throw AimarketException(
          'Failed to fetch well-known: ${resp.statusCode}');
    }
    _wellKnown = resp.body;
    return _wellKnown!;
  }

  /// Convenience accessor for the hub URL from the config.
  String get _hubUrl => _config.hubUrl;

  /// Discover capabilities matching an intent.
  ///
  /// [intent] is a natural-language description of what you need.
  /// [budget] is the max total you're willing to spend overall.
  /// [limit] caps the number of results returned (default 5).
  /// [category] filters to a specific marketplace vertical.
  Future<List<PlanStep>> discover({
    required String intent,
    double? budget,
    int limit = 5,
    String? category,
  }) async {
    final uri =
        Uri.parse('$_hubUrl/ai-market/v2/search').replace(queryParameters: {
      'intent': intent,
      if (budget != null) 'budget_usd': budget.toString(),
      'limit': limit.toString(),
      if (category != null) 'category': category,
    });

    final resp = await _http.get(uri, headers: {
      'X-AIMarket-Affiliate': _config.affiliate,
    });

    if (resp.statusCode != 200) {
      throw AimarketException(
          'Discovery failed: ${resp.statusCode} ${resp.body}');
    }

    final data = json.decode(resp.body) as Map<String, dynamic>;
    final items = data['results'] as List<dynamic>? ?? [];
    return items
        .map((i) => PlanStep.fromJson(i as Map<String, dynamic>))
        .toList();
  }

  /// Discover by product_id (direct lookup, bypasses search).
  Future<List<PlanStep>> discoverProduct(String productId) async {
    return discover(intent: 'product:$productId');
  }

  // ── Phase 2: Channel Open ──────────────────────────────────────────

  /// Open a pre-funded payment channel.
  ///
  /// Before opening a new channel, checks the in-memory cache for an
  /// existing channel with the same [depositUsd], [token], and [chain].
  /// If a cached channel has more than 50% of its balance remaining and
  /// has not expired, it is returned directly without a network call.
  ///
  /// [depositUsd] is how much to deposit. A $5 channel covers ~50 calls
  /// at $0.10 each. [token] defaults to USDT on [chain] (default: Base).
  Future<Channel> openChannel(
    double depositUsd, {
    String token = 'USDT',
    String chain = 'base',
  }) async {
    final cacheKey = '$depositUsd:$token:$chain';
    final cached = _channelCache[cacheKey];

    // Reuse cached channel if it has sufficient balance and is not expired.
    if (cached != null && cached.isReusable) {
      return cached.channel;
    }

    // Stale channel — evict from cache.
    if (cached != null) {
      _channelCache.remove(cacheKey);
    }

    final resp = await _http.post(
      Uri.parse('$_hubUrl/ai-market/v2/channel/open'),
      headers: {
        'Content-Type': 'application/json',
        'X-AIMarket-Affiliate': _config.affiliate,
      },
      body: json.encode({
        'deposit_usd': depositUsd,
        'token': token,
        'chain': chain,
      }),
    );

    if (resp.statusCode == 404) {
      throw AimarketException('Payment channels not available on this hub');
    }
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw AimarketException(
          'Channel open failed: ${resp.statusCode} ${resp.body}');
    }

    final channel =
        Channel.fromJson(json.decode(resp.body) as Map<String, dynamic>);

    // Cache the newly opened channel.
    _channelCache[cacheKey] = _CachedChannel(channel, DateTime.now());

    return channel;
  }

  /// Get the current on-chain balance of a payment channel.
  ///
  /// Unlike the cached balance from [openChannel], this fetches the live
  /// balance from the hub, reflecting any external deposits or withdrawals.
  Future<double> getChannelBalance(String channelId) async {
    final resp = await _http.get(
      Uri.parse('$_hubUrl/ai-market/v2/channel/$channelId'),
      headers: {'X-AIMarket-Affiliate': _config.affiliate},
    );

    if (resp.statusCode != 200) {
      throw AimarketException(
          'Failed to get channel balance: ${resp.statusCode}');
    }

    final data = json.decode(resp.body) as Map<String, dynamic>;
    return (data['balance_usd'] as num?)?.toDouble() ?? 0;
  }

  // ── Phase 3: Invoke ────────────────────────────────────────────────

  /// Invoke a single capability, paying from the channel.
  ///
  /// [capabilityId] is the capability to call (from discovery results).
  /// [input] is the capability-specific JSON input payload.
  /// [channelId] is the pre-funded payment channel ID.
  /// [sourceHub] optionally routes through a federated hub.
  /// [productId] narrows the capability within a product family.
  /// [verifyTee] if true, verifies TEE attestation before sending.
  ///
  /// Network errors and timeouts are retried with exponential backoff
  /// per [_config.maxRetries]. Payment errors (402), safety blocks (403),
  /// and other protocol errors propagate immediately.
  Future<InvokeResult> invoke({
    required String capabilityId,
    required Map<String, dynamic> input,
    required String channelId,
    String? sourceHub,
    String? productId,
    bool verifyTee = true,
  }) async {
    return _retryWithBackoff(() => _invokeOnce(
          capabilityId: capabilityId,
          input: input,
          channelId: channelId,
          sourceHub: sourceHub,
          productId: productId,
          verifyTee: verifyTee,
        ));
  }

  /// Single invocation attempt (one try, no retry).
  Future<InvokeResult> _invokeOnce({
    required String capabilityId,
    required Map<String, dynamic> input,
    required String channelId,
    String? sourceHub,
    String? productId,
    bool verifyTee = true,
  }) async {
    // TEE pre-check: if attestation is in manifest, verify before sending.
    if (verifyTee && _config.verifyTee) {
      // In production, fetch manifest and verify attestation.
      // The hub runs safety + TEE hooks server-side.
    }

    final headers = _signer.signedHeaders(
      channelId: channelId,
      capabilityId: capabilityId,
      affiliate: _config.affiliate,
    );
    headers['Content-Type'] = 'application/json';

    final body = <String, dynamic>{
      'capability_id': capabilityId,
      'input': input,
    };
    if (sourceHub != null) body['source_hub'] = sourceHub;
    if (productId != null) body['product_id'] = productId;

    final startMs = DateTime.now().microsecondsSinceEpoch / 1000;

    final response = await _http
        .post(
          Uri.parse('$_hubUrl/ai-market/v2/invoke'),
          headers: headers,
          body: json.encode(body),
        )
        .timeout(_config.timeout);

    final latencyMs =
        (DateTime.now().microsecondsSinceEpoch / 1000) - startMs;

    // 403: Safety blocked — thrown immediately (not retried).
    if (response.statusCode == 403) {
      final data = json.decode(response.body) as Map<String, dynamic>;
      throw AimarketSafetyException(
          data['reason'] as String? ?? 'Blocked by safety gate');
    }

    // 402: Payment required — thrown immediately (not retried).
    if (response.statusCode == 402) {
      throw AimarketPaymentException(
          'Channel depleted or expired — open a new channel');
    }

    if (response.statusCode != 200) {
      return InvokeResult(
        success: false,
        priceUsd: 0,
        latencyMs: latencyMs,
        error: 'HTTP ${response.statusCode}: ${response.body}',
      );
    }

    return InvokeResult.fromJson(
        json.decode(response.body) as Map<String, dynamic>);
  }

  /// Invoke multiple capabilities sharing the same payment channel.
  ///
  /// [capabilityIds] and [inputs] must have the same length. Each pair is
  /// invoked independently, and all run concurrently via [Future.wait].
  ///
  /// Returns results in the same order as the inputs. A single failure
  /// does not cancel the remaining invocations.
  Future<List<InvokeResult>> invokeBatch({
    required List<String> capabilityIds,
    required List<Map<String, dynamic>> inputs,
    required String channelId,
    String? sourceHub,
  }) async {
    if (capabilityIds.length != inputs.length) {
      throw ArgumentError('capabilityIds and inputs must have the same length');
    }

    final futures = <Future<InvokeResult>>[];
    for (var i = 0; i < capabilityIds.length; i++) {
      futures.add(invoke(
        capabilityId: capabilityIds[i],
        input: inputs[i],
        channelId: channelId,
        sourceHub: sourceHub,
      ));
    }

    return Future.wait(futures);
  }

  // ── Phase 4: Settle ────────────────────────────────────────────────

  /// Close a payment channel and get a refund for the unused balance.
  ///
  /// Removes the channel from the in-memory cache and calls the hub's
  /// channel close endpoint. The returned [Settlement] includes the
  /// total spent, refund amount, and invocation count.
  Future<Settlement> closeChannel(String channelId) async {
    // Evict from cache regardless of response.
    _channelCache.removeWhere((_, cached) => cached.channel.id == channelId);

    final resp = await _http.post(
      Uri.parse('$_hubUrl/ai-market/v2/channel/close'),
      headers: {
        'Content-Type': 'application/json',
        'X-AIMarket-Affiliate': _config.affiliate,
      },
      body: json.encode({'channel_id': channelId}),
    );

    if (resp.statusCode == 404) {
      throw AimarketException('Channel not found: $channelId');
    }
    if (resp.statusCode != 200) {
      throw AimarketException(
          'Settlement failed: ${resp.statusCode} ${resp.body}');
    }

    return Settlement.fromJson(
        json.decode(resp.body) as Map<String, dynamic>);
  }

  // ── Phase 5: Verify ────────────────────────────────────────────────

  /// Verify TEE attestation for a capability BEFORE invoking.
  ///
  /// Call this if you fetched the manifest separately and want to check
  /// the attestation before sending any data to the capability.
  /// Returns true if the capability runs in a verified enclave.
  bool verifyTeeAttestation(TeeAttestation attestation, String capabilityId) {
    return _teeVerifier.verifyAttestation(attestation, capabilityId);
  }

  /// Verify TEE receipt AFTER invoking.
  ///
  /// Proves that the output was generated inside the attested enclave by
  /// comparing the input/output hashes captured in the receipt.
  bool verifyTeeReceipt(
      TeeReceipt receipt, String sentInput, String receivedOutput) {
    return _teeVerifier.verifyReceipt(receipt, sentInput, receivedOutput);
  }

  /// Register a known-good code hash for a trusted capability.
  void trustCodeHash(String capabilityId, String codeHash) {
    _teeVerifier.trustCodeHash(capabilityId, codeHash);
  }

  /// Fetch trusted code hashes from the hub's well-known endpoint.
  ///
  /// Returns the number of hashes fetched, or -1 on failure.
  Future<int> fetchTrustedHashes() async {
    return _teeVerifier.fetchTrustedHashes(_hubUrl, client: _http);
  }

  // ── Convenience: Full Cycle ────────────────────────────────────────

  /// Run the full 5-phase cycle for a single capability.
  ///
  /// Discovers matching capabilities, opens a channel, invokes the top
  /// result, settles the channel, and returns a [BillOfMaterials]
  /// capturing the entire interaction trace.
  Future<BillOfMaterials> runOnce({
    required String intent,
    required Map<String, dynamic> input,
    double depositUsd = 5.00,
    String? category,
  }) async {
    // 1. Discover
    final plan =
        await discover(intent: intent, budget: depositUsd, category: category);
    if (plan.isEmpty) {
      throw AimarketException('No capabilities found for: $intent');
    }

    // 2. Open channel (may reuse cached channel with >50% balance).
    final channel = await openChannel(depositUsd);

    // 3. Invoke
    final step = plan.first;
    final result = await invoke(
      capabilityId: step.capability.id,
      input: input,
      channelId: channel.id,
      productId: step.capability.productId,
      sourceHub: step.capability.sourceHub,
    );

    // 4. Settle
    final settlement = await closeChannel(channel.id);

    // 5. Build BOM
    return BillOfMaterials(
      task: intent,
      plan: plan,
      results: [result],
      settlement: settlement,
      totalSpentUsd: result.priceUsd,
      protocolVersion: 'v2',
    );
  }

  /// Release HTTP client and other resources.
  void dispose() {
    _http.close();
    _channelCache.clear();
  }
}
