import 'package:aimarket_agent/aimarket_agent.dart';

import 'dev_wallet.dart';

/// Hub connection with AI Market Protocol v2 economics (discover → channel → invoke).
class HubSession {
  HubSession({
    this.hubUrl = kAicomDefaultHubUrl,
    String? walletKey,
    this.affiliate = 'aicom-desktop',
  }) : walletKey = walletKey ?? '';

  final String hubUrl;
  final String walletKey;
  final String affiliate;

  bool get walletConfigured => walletKey.isNotEmpty;

  AimarketAgent? _agent;
  Channel? _channel;
  double _sessionSpendUsd = 0;

  bool get isConnected => _agent != null;
  double get sessionSpendUsd => _sessionSpendUsd;
  double? get channelBalanceUsd => _channel?.balanceUsd;

  AimarketAgent get agent {
    if (_agent == null) {
      throw StateError('Hub not connected');
    }
    return _agent!;
  }

  void connect() {
    if (walletKey.isEmpty) return;
    _agent?.dispose();
    _agent = AimarketAgent(
      hubUrl: hubUrl,
      walletKey: walletKey,
      affiliate: affiliate,
    );
  }

  Future<List<PlanStep>> discover({
    required String intent,
    String? category,
    double budget = 5,
  }) async {
    connect();
    return agent.discover(intent: intent, category: category, budget: budget);
  }

  Future<Channel> ensureChannel({double depositUsd = 5}) async {
    connect();
    if (_channel != null && (_channel!.balanceUsd) > 0.5) {
      return _channel!;
    }
    _channel = await agent.openChannel(depositUsd);
    return _channel!;
  }

  Future<InvokeResult> invoke({
    required String capabilityId,
    required Map<String, dynamic> input,
    String? productId,
  }) async {
    final ch = await ensureChannel();
    final result = await agent.invoke(
      capabilityId: capabilityId,
      input: input,
      channelId: ch.id,
      productId: productId,
    );
    _sessionSpendUsd += result.priceUsd;
    return result;
  }

  void dispose() {
    _agent?.dispose();
    _agent = null;
    _channel = null;
  }
}
