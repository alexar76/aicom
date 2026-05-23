import 'package:aimarket_agent/aimarket_agent.dart';

/// Wraps the AIMarketAgent for the Creator Algorithm Coach domain.
///
/// Handles discovery of algorithm-signal capabilities, purchasing
/// verified performance data, and selling TEE-proven creator metrics
/// back to the marketplace.
class MarketplaceService {
  final String hubUrl;
  AimarketAgent? _agent;

  MarketplaceService({required this.hubUrl});

  /// Initialize the agent with a wallet key.
  void connect(String walletKey) {
    _agent = AimarketAgent(
      hubUrl: hubUrl,
      walletKey: walletKey,
      affiliate: 'creator-algorithm-coach',
    );
  }

  AimarketAgent get agent {
    if (_agent == null) {
      throw StateError('MarketplaceService not connected. Call connect() first.');
    }
    return _agent!;
  }

  bool get isConnected => _agent != null;

  /// Discover algorithm signal capabilities for a platform & niche.
  Future<List<PlanStep>> discoverAlgorithmSignals({
    required String platform,
    required String niche,
    double budget = 5.00,
  }) async {
    return agent.discover(
      intent: 'algorithm signals for $platform $niche - posting times, trend windows, hook structures',
      budget: budget,
      category: 'creator',
    );
  }

  /// Buy verified performance data for a specific hook/structure.
  Future<InvokeResult> buyHookPerformance({
    required String capabilityId,
    required String channelId,
    required String hookType,
    required String platform,
  }) async {
    return agent.invoke(
      capabilityId: capabilityId,
      channelId: channelId,
      input: {
        'hook_type': hookType,
        'platform': platform,
        'include_tee_proof': true,
      },
      verifyTee: true,
    );
  }

  /// Sell verified creator metrics to the marketplace.
  ///
  /// Creator metrics include posting times, engagement rates, and
  /// hook conversion data — all TEE-proven to prevent faking.
  Future<InvokeResult> sellVerifiedMetrics({
    required String capabilityId,
    required String channelId,
    required Map<String, dynamic> metrics,
  }) async {
    return agent.invoke(
      capabilityId: capabilityId,
      channelId: channelId,
      input: {
        'action': 'publish_metrics',
        'metrics': metrics,
        'tee_attestation': true,
      },
      verifyTee: true,
    );
  }

  /// Open a pre-funded channel for purchasing signals.
  Future<Channel> openSignalChannel({double depositUsd = 5.00}) async {
    return agent.openChannel(depositUsd);
  }

  /// Close channel and reclaim unused balance.
  Future<Settlement> closeChannel(String channelId) async {
    return agent.closeChannel(channelId);
  }

  /// Run the full buy cycle: discover, open channel, invoke, settle.
  Future<BillOfMaterials> buyAlgorithmSignals({
    required String platform,
    required String niche,
    double budget = 5.00,
  }) async {
    return agent.runOnce(
      intent: 'algorithm signals for $platform $niche - posting times, trend windows, hook structure benchmarks',
      input: {
        'platform': platform,
        'niche': niche,
        'include_tee_proof': true,
      },
      depositUsd: budget,
      category: 'creator',
    );
  }

  void dispose() {
    _agent?.dispose();
    _agent = null;
  }
}
