/// Capability Composer — Desktop pipeline builder for the AI Market Protocol.
///
/// Visual node-graph editor where users discover marketplace capabilities,
/// chain them into pipelines, execute them, and sell the resulting pipelines
/// as purchasable templates.
///
/// ## Architecture
///
/// The app uses a three-layer architecture:
///   1. UI Layer    — Flutter Material widgets with a CustomPainter node graph
///   2. Engine      — Pipeline DAG model with topological executor
///   3. SDK Layer   — aimarket_agent for discovery, payment, and invocation
library;

import 'dart:convert';
import 'dart:math';

import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import 'package:aimarket_agent/aimarket_agent.dart';

import 'l10n/app_strings.dart';

const _appId = 'capability-composer';

// ═══════════════════════════════════════════════════════════════════════════════
// Entry Point
// ═══════════════════════════════════════════════════════════════════════════════

void main() {
  runApp(
    AicomLocalizedApp(
      appId: _appId,
      appStrings: AppStrings.catalog,
      collectBackupData: () async => {
        'preferences': await collectPreferencesBackup(_appId),
      },
      restoreBackupData: (data) async {
        final prefs = data['preferences'];
        if (prefs is Map) await restorePreferencesBackup(Map<String, dynamic>.from(prefs));
      },
      builder: (context, locale) => ChangeNotifierProvider(
        create: (_) => PipelineState(),
        child: MaterialApp(
          title: context.t('appTitle'),
          debugShowCheckedModeBanner: false,
          locale: locale.activeFlutterLocale,
          supportedLocales: AicomLocalization.localesFor(locale),
          localizationsDelegates: AicomLocalization.delegates,
          theme: AicomDesktopTheme.light(seed: AicomProductColors.capabilityComposer),
          darkTheme: AicomDesktopTheme.dark(seed: AicomProductColors.capabilityComposer),
          themeMode: ThemeMode.system,
          home: const ComposerShell(),
        ),
      ),
    ),
  );
}

class CapabilityComposerApp extends StatelessWidget {
  const CapabilityComposerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const ComposerShell();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Data Models
// ═══════════════════════════════════════════════════════════════════════════════

/// A single node in the pipeline graph, wrapping a marketplace capability.
class PipelineNode {
  final String id;
  final String label;
  final Capability capability;
  Offset position;
  NodeExecutionState state;
  Map<String, dynamic>? cachedOutput;

  PipelineNode({
    required this.id,
    required this.label,
    required this.capability,
    this.position = Offset.zero,
    this.state = NodeExecutionState.idle,
    this.cachedOutput,
  });
}

/// Execution state of a pipeline node.
enum NodeExecutionState { idle, queued, running, success, failed }

/// An edge connecting two nodes in the pipeline graph.
class DataEdge {
  final String id;
  final String sourceNodeId;
  final String targetNodeId;

  const DataEdge({
    required this.id,
    required this.sourceNodeId,
    required this.targetNodeId,
  });
}

/// A directed acyclic graph of marketplace capabilities.
class PipelineDag {
  final String id;
  final String name;
  final String description;
  final List<PipelineNode> nodes;
  final List<DataEdge> edges;

  PipelineDag({
    required this.id,
    required this.name,
    this.description = '',
    required this.nodes,
    required this.edges,
  });

  /// Serialize to the standard pipeline format.
  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'description': description,
        'nodes': nodes.map((n) => {
          'id': n.id,
          'capability_id': n.capability.id,
          'product_id': n.capability.productId,
          'source_hub': n.capability.sourceHub,
          'name': n.label,
          'position': {'x': n.position.dx, 'y': n.position.dy},
        }).toList(),
        'edges': edges.map((e) => {
          'id': e.id,
          'source_node': e.sourceNodeId,
          'target_node': e.targetNodeId,
        }).toList(),
      };
}

/// Result of a full pipeline execution.
class PipelineReceipt {
  final String pipelineId;
  final Map<String, InvokeResult> nodeResults;
  final Settlement? settlement;
  final DateTime executedAt;

  const PipelineReceipt({
    required this.pipelineId,
    required this.nodeResults,
    this.settlement,
    required this.executedAt,
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// Application State
// ═══════════════════════════════════════════════════════════════════════════════

/// Central application state managed via Provider.
class PipelineState extends ChangeNotifier {
  final _uuid = const Uuid();

  // ── Connection ──
  String _hubUrl = 'https://hub.aicom.io';
  String? _walletKey;
  AimarketAgent? _agent;
  bool _connected = false;
  String? _statusMessage;

  // ── Pipeline ──
  final List<PipelineDag> _pipelines = [];
  int _activePipelineIndex = 0;
  String? _selectedNodeId;

  // ── Discovered capabilities ──
  final List<Capability> _discoveredCaps = [];
  bool _discovering = false;
  String? _discoveryError;

  // ── Getters ──

  bool get connected => _connected;
  String? get statusMessage => _statusMessage;
  List<PipelineDag> get pipelines => List.unmodifiable(_pipelines);
  PipelineDag? get activePipeline =>
      _pipelines.isNotEmpty ? _pipelines[_activePipelineIndex] : null;
  String? get selectedNodeId => _selectedNodeId;
  List<Capability> get discoveredCaps => List.unmodifiable(_discoveredCaps);
  bool get discovering => _discovering;
  String? get discoveryError => _discoveryError;
  String get hubUrl => _hubUrl;

  // ── Connection ──

  void updateHubUrl(String url) {
    _hubUrl = url;
    _connected = false;
    _agent?.dispose();
    _agent = null;
    notifyListeners();
  }

  Future<void> connect(String walletKey) async {
    _walletKey = walletKey;
    _statusMessage = 'Connecting...';
    notifyListeners();

    try {
      _agent = AimarketAgent(
        hubUrl: _hubUrl,
        walletKey: walletKey,
        affiliate: 'capability-composer-v1',
      );

      // Verify connection by fetching well-known
      await _agent!.wellKnown;

      _connected = true;
      _statusMessage = 'Connected to $_hubUrl';
    } catch (e) {
      _connected = false;
      _statusMessage = 'Connection failed: $e';
    }
    notifyListeners();
  }

  // ── Pipeline Management ──

  void createPipeline(String name) {
    final pipeline = PipelineDag(
      id: _uuid.v4(),
      name: name,
      nodes: [],
      edges: [],
    );
    _pipelines.add(pipeline);
    _activePipelineIndex = _pipelines.length - 1;
    _selectedNodeId = null;
    notifyListeners();
  }

  void selectPipeline(int index) {
    if (index >= 0 && index < _pipelines.length) {
      _activePipelineIndex = index;
      _selectedNodeId = null;
      notifyListeners();
    }
  }

  void selectNode(String? nodeId) {
    _selectedNodeId = nodeId;
    notifyListeners();
  }

  PipelineNode? get selectedNode {
    if (_selectedNodeId == null) return null;
    return activePipeline?.nodes.where((n) => n.id == _selectedNodeId).firstOrNull;
  }

  void addNode(Capability capability, Offset position) {
    final pipeline = activePipeline;
    if (pipeline == null) return;

    final node = PipelineNode(
      id: _uuid.v4(),
      label: capability.name,
      capability: capability,
      position: position,
    );

    // Find the pipeline by index to mutate it
    _pipelines[_activePipelineIndex] = PipelineDag(
      id: pipeline.id,
      name: pipeline.name,
      description: pipeline.description,
      nodes: [...pipeline.nodes, node],
      edges: pipeline.edges,
    );

    _selectedNodeId = node.id;
    notifyListeners();
  }

  void removeNode(String nodeId) {
    final pipeline = activePipeline;
    if (pipeline == null) return;

    _pipelines[_activePipelineIndex] = PipelineDag(
      id: pipeline.id,
      name: pipeline.name,
      description: pipeline.description,
      nodes: pipeline.nodes.where((n) => n.id != nodeId).toList(),
      edges: pipeline.edges
          .where((e) => e.sourceNodeId != nodeId && e.targetNodeId != nodeId)
          .toList(),
    );

    if (_selectedNodeId == nodeId) _selectedNodeId = null;
    notifyListeners();
  }

  void addEdge(String sourceId, String targetId) {
    final pipeline = activePipeline;
    if (pipeline == null) return;

    // Don't add duplicate edges
    final exists = pipeline.edges.any(
      (e) => e.sourceNodeId == sourceId && e.targetNodeId == targetId,
    );
    if (exists) return;

    // Don't allow self-connections
    if (sourceId == targetId) return;

    _pipelines[_activePipelineIndex] = PipelineDag(
      id: pipeline.id,
      name: pipeline.name,
      description: pipeline.description,
      nodes: pipeline.nodes,
      edges: [
        ...pipeline.edges,
        DataEdge(
          id: _uuid.v4(),
          sourceNodeId: sourceId,
          targetNodeId: targetId,
        ),
      ],
    );
    notifyListeners();
  }

  void removeEdge(String edgeId) {
    final pipeline = activePipeline;
    if (pipeline == null) return;

    _pipelines[_activePipelineIndex] = PipelineDag(
      id: pipeline.id,
      name: pipeline.name,
      description: pipeline.description,
      nodes: pipeline.nodes,
      edges: pipeline.edges.where((e) => e.id != edgeId).toList(),
    );
    notifyListeners();
  }

  void updateNodePosition(String nodeId, Offset position) {
    final pipeline = activePipeline;
    if (pipeline == null) return;

    final updatedNodes = pipeline.nodes.map((n) {
      if (n.id == nodeId) {
        return PipelineNode(
          id: n.id,
          label: n.label,
          capability: n.capability,
          position: position,
          state: n.state,
          cachedOutput: n.cachedOutput,
        );
      }
      return n;
    }).toList();

    _pipelines[_activePipelineIndex] = PipelineDag(
      id: pipeline.id,
      name: pipeline.name,
      description: pipeline.description,
      nodes: updatedNodes,
      edges: pipeline.edges,
    );
    // Don't notify on every drag pixel — caller batches
    notifyListeners();
  }

  // ── Discovery ──

  Future<void> discoverCapabilities({
    required String intent,
    double? budget,
    String? category,
  }) async {
    if (_agent == null) return;

    _discovering = true;
    _discoveryError = null;
    _discoveredCaps.clear();
    notifyListeners();

    try {
      final results = await _agent!.discover(
        intent: intent,
        budget: budget,
        category: category,
        limit: 10,
      );
      _discoveredCaps.addAll(results.map((r) => r.capability));
    } catch (e) {
      _discoveryError = e.toString();
    }

    _discovering = false;
    notifyListeners();
  }

  // ── Execution ──

  Future<PipelineReceipt?> executeActivePipeline(
    Map<String, dynamic> pipelineInput,
  ) async {
    final pipeline = activePipeline;
    if (pipeline == null || _agent == null) return null;

    // Mark all nodes as queued
    _updateAllNodeStates(NodeExecutionState.queued);
    notifyListeners();

    try {
      // Open a single channel for the pipeline
      final totalCost = pipeline.nodes.fold<double>(
        0,
        (sum, n) => sum + n.capability.pricePerCallUsd,
      );
      final channel = await _agent!.openChannel(
        totalCost * 1.2,
        token: 'USDT',
        chain: 'base',
      );

      // Simple sequential execution
      final results = <String, InvokeResult>{};
      for (final node in pipeline.nodes) {
        _setNodeState(node.id, NodeExecutionState.running);
        notifyListeners();

        try {
          final result = await _agent!.invoke(
            capabilityId: node.capability.id,
            input: pipelineInput,
            channelId: channel.id,
            productId: node.capability.productId,
            sourceHub: node.capability.sourceHub,
          );

          results[node.id] = result;
          _setNodeState(
            node.id,
            result.success ? NodeExecutionState.success : NodeExecutionState.failed,
          );
        } catch (e) {
          results[node.id] = InvokeResult(
            success: false,
            priceUsd: 0,
            latencyMs: 0,
            error: e.toString(),
          );
          _setNodeState(node.id, NodeExecutionState.failed);
        }
        notifyListeners();
      }

      final settlement = await _agent!.closeChannel(channel.id);

      return PipelineReceipt(
        pipelineId: pipeline.id,
        nodeResults: results,
        settlement: settlement,
        executedAt: DateTime.now().toUtc(),
      );
    } catch (e) {
      _updateAllNodeStates(NodeExecutionState.failed);
      notifyListeners();
      rethrow;
    }
  }

  // ── Serialization ──

  String serializePipeline() {
    final pipeline = activePipeline;
    if (pipeline == null) return '{}';
    return const JsonEncoder.withIndent('  ').convert(pipeline.toJson());
  }

  // ── Helpers ──

  void _updateAllNodeStates(NodeExecutionState state) {
    final pipeline = activePipeline;
    if (pipeline == null) return;

    final updatedNodes = pipeline.nodes.map((n) {
      return PipelineNode(
        id: n.id,
        label: n.label,
        capability: n.capability,
        position: n.position,
        state: state,
        cachedOutput: n.cachedOutput,
      );
    }).toList();

    _pipelines[_activePipelineIndex] = PipelineDag(
      id: pipeline.id,
      name: pipeline.name,
      description: pipeline.description,
      nodes: updatedNodes,
      edges: pipeline.edges,
    );
  }

  void _setNodeState(String nodeId, NodeExecutionState state) {
    final pipeline = activePipeline;
    if (pipeline == null) return;

    final updatedNodes = pipeline.nodes.map((n) {
      if (n.id == nodeId) {
        return PipelineNode(
          id: n.id,
          label: n.label,
          capability: n.capability,
          position: n.position,
          state: state,
          cachedOutput: n.cachedOutput,
        );
      }
      return n;
    }).toList();

    _pipelines[_activePipelineIndex] = PipelineDag(
      id: pipeline.id,
      name: pipeline.name,
      description: pipeline.description,
      nodes: updatedNodes,
      edges: pipeline.edges,
    );
  }

  @override
  void dispose() {
    _agent?.dispose();
    super.dispose();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Shell — Top-level navigation layout
// ═══════════════════════════════════════════════════════════════════════════════

class ComposerShell extends StatefulWidget {
  const ComposerShell({super.key});

  @override
  State<ComposerShell> createState() => _ComposerShellState();
}

class _ComposerShellState extends State<ComposerShell> {
  int _selectedIndex = 0;
  final _walletKey = walletKeyFromEnvironment();
  late final HubSession _hub;

  static const _screens = <Widget>[
    PipelineCanvas(),
    CapabilityBrowser(),
    TemplatesMarketplace(),
  ];

  @override
  void initState() {
    super.initState();
    _hub = HubSession(affiliate: _appId, walletKey: _walletKey);
    if (_walletKey != null) _hub.connect();
  }

  @override
  void dispose() {
    _hub.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          MarketplaceEconomicsBar(
            hubLabel: _hub.isConnected ? _hub.hubUrl : 'Hub offline',
            walletConfigured: _walletKey != null,
            channelBalanceUsd: _hub.channelBalanceUsd,
            sessionSpendUsd: _hub.sessionSpendUsd,
          ),
          Expanded(
            child: Row(
              children: [
                NavigationRail(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: (i) => setState(() => _selectedIndex = i),
                  labelType: NavigationRailLabelType.all,
                  leading: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.account_tree_rounded, size: 32,
                            color: Theme.of(context).colorScheme.primary),
                        const SizedBox(height: 4),
                        Text('Composer', style: Theme.of(context).textTheme.labelSmall),
                      ],
                    ),
                  ),
                  destinations: [
                    NavigationRailDestination(
                      icon: const Icon(Icons.dashboard),
                      selectedIcon: const Icon(Icons.dashboard_rounded),
                      label: Text(context.t('navCanvas')),
                    ),
                    NavigationRailDestination(
                      icon: const Icon(Icons.search),
                      selectedIcon: const Icon(Icons.search_rounded),
                      label: Text(context.t('navDiscover')),
                    ),
                    NavigationRailDestination(
                      icon: const Icon(Icons.storefront),
                      selectedIcon: const Icon(Icons.storefront_rounded),
                      label: Text(context.t('navTemplates')),
                    ),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(child: _screens[_selectedIndex]),
                const Padding(
                  padding: EdgeInsets.only(right: 8),
                  child: AicomSettingsButton(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Pipeline Canvas — Node graph editor
// ═══════════════════════════════════════════════════════════════════════════════

class PipelineCanvas extends StatelessWidget {
  const PipelineCanvas({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PipelineState>(
      builder: (context, state, _) {
        final pipeline = state.activePipeline;

        return Scaffold(
          appBar: AppBar(
            title: Text(pipeline?.name ?? 'No Pipeline'),
            actions: [
              if (state.connected)
                PopupMenuButton<String>(
                  icon: const Icon(Icons.wallet),
                  tooltip: 'Connected',
                  itemBuilder: (_) => [
                    const PopupMenuItem(value: 'disconnect', child: Text('Disconnect')),
                  ],
                )
              else
                TextButton.icon(
                  icon: const Icon(Icons.link),
                  label: const Text('Connect'),
                  onPressed: () => _showConnectDialog(context),
                ),
              const SizedBox(width: 8),
              if (pipeline != null) ...[
                IconButton(
                  icon: const Icon(Icons.play_arrow_rounded),
                  tooltip: 'Execute pipeline',
                  onPressed: () => _executePipeline(context, state),
                ),
                IconButton(
                  icon: const Icon(Icons.download),
                  tooltip: 'Export pipeline',
                  onPressed: () => _showExportDialog(context, state),
                ),
                IconButton(
                  icon: const Icon(Icons.publish),
                  tooltip: 'Publish as template',
                  onPressed: () => _showPublishDialog(context, state),
                ),
              ],
            ],
          ),
          body: pipeline == null
              ? _buildEmptyState(context, state)
              : _buildCanvas(context, state, pipeline),
          floatingActionButton: pipeline != null
              ? FloatingActionButton.small(
                  onPressed: () => state.addNode(
                    Capability(
                      id: 'node-${DateTime.now().millisecondsSinceEpoch}',
                      productId: 'custom',
                      name: 'New Capability',
                      version: '1.0',
                      description: 'Drop a discovered capability here',
                      pricePerCallUsd: 0.10,
                      sourceHub: state.hubUrl,
                    ),
                    Offset(
                      100 + Random().nextDouble() * 300,
                      100 + Random().nextDouble() * 200,
                    ),
                  ),
                  tooltip: 'Add capability node',
                  child: const Icon(Icons.add),
                )
              : null,
        );
      },
    );
  }

  Widget _buildEmptyState(BuildContext context, PipelineState state) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.account_tree_outlined,
              size: 80, color: Theme.of(context).colorScheme.outline),
          const SizedBox(height: 24),
          Text('No Pipeline Open',
              style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text('Create a new pipeline to start composing capabilities.',
              style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 24),
          FilledButton.icon(
            icon: const Icon(Icons.add),
            label: const Text('New Pipeline'),
            onPressed: () => _showNewPipelineDialog(context, state),
          ),
        ],
      ),
    );
  }

  Widget _buildCanvas(
      BuildContext context, PipelineState state, PipelineDag pipeline) {
    return Stack(
      children: [
        // Node graph area
        Positioned.fill(
          child: CustomPaint(
            painter: _EdgePainter(
              pipeline: pipeline,
              color: Theme.of(context).colorScheme.primary,
            ),
            child: Stack(
              children: pipeline.nodes.map((node) {
                return Positioned(
                  left: node.position.dx,
                  top: node.position.dy,
                  child: _NodeCard(
                    node: node,
                    isSelected: state.selectedNodeId == node.id,
                    onTap: () => state.selectNode(node.id),
                    onDrag: (delta) => state.updateNodePosition(
                      node.id,
                      node.position + delta,
                    ),
                    onDelete: () => state.removeNode(node.id),
                  ),
                );
              }).toList(),
            ),
          ),
        ),
        // Minimap / status bar
        Positioned(
          left: 8,
          bottom: 8,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              '${pipeline.nodes.length} nodes | ${pipeline.edges.length} edges',
              style: Theme.of(context).textTheme.labelSmall,
            ),
          ),
        ),
        // Connection status
        Positioned(
          right: 8,
          bottom: 8,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: state.connected
                  ? Colors.green.withAlpha(30)
                  : Colors.orange.withAlpha(30),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  state.connected ? Icons.check_circle : Icons.warning,
                  size: 14,
                  color: state.connected ? Colors.green : Colors.orange,
                ),
                const SizedBox(width: 4),
                Text(
                  state.connected ? 'Connected' : 'Disconnected',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ],
            ),
          ),
        ),
        // Top-left: new pipeline button
        Positioned(
          left: 8,
          top: 8,
          child: Tooltip(
            message: 'New pipeline',
            child: IconButton(
              icon: const Icon(Icons.add_circle_outline),
              onPressed: () => _showNewPipelineDialog(context, state),
            ),
          ),
        ),
      ],
    );
  }

  void _showNewPipelineDialog(BuildContext context, PipelineState state) {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New Pipeline'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: 'e.g., LinkedIn -> Email -> CRM',
            labelText: 'Pipeline name',
          ),
          onSubmitted: (value) {
            if (value.trim().isNotEmpty) {
              state.createPipeline(value.trim());
              Navigator.of(ctx).pop();
            }
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (controller.text.trim().isNotEmpty) {
                state.createPipeline(controller.text.trim());
                Navigator.of(ctx).pop();
              }
            },
            child: const Text('Create'),
          ),
        ],
      ),
    );
  }

  void _showConnectDialog(BuildContext context) {
    final urlController = TextEditingController(text: 'https://hub.aicom.io');
    final keyController = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Connect to AI Market'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: urlController,
              decoration: const InputDecoration(
                labelText: 'Hub URL',
                hintText: 'https://hub.aicom.io',
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: keyController,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Wallet Private Key',
                hintText: 'Enter your wallet private key hex',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final state = context.read<PipelineState>();
              state.updateHubUrl(urlController.text.trim());
              state.connect(keyController.text.trim());
              Navigator.of(ctx).pop();
            },
            child: const Text('Connect'),
          ),
        ],
      ),
    );
  }

  void _showExportDialog(BuildContext context, PipelineState state) {
    final json = state.serializePipeline();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Export Pipeline'),
        content: SizedBox(
          width: 500,
          child: SelectableText(
            json,
            style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
          ),
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  void _showPublishDialog(BuildContext context, PipelineState state) {
    final priceController = TextEditingController(text: '4.99');
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Publish as Template'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Publish "${state.activePipeline?.name}" to the marketplace as a purchasable template?',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: priceController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Price (USD)',
                prefixText: '\$ ',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              // In production: POST /ai-market/v2/product/publish
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    'Pipeline published at \$${priceController.text} USD (simulated)',
                  ),
                ),
              );
              Navigator.of(ctx).pop();
            },
            child: const Text('Publish'),
          ),
        ],
      ),
    );
  }

  void _executePipeline(BuildContext context, PipelineState state) async {
    if (!state.connected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Connect to a hub first')),
      );
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Pipeline execution started...')),
    );

    try {
      final receipt = await state.executeActivePipeline({});
      if (receipt != null) {
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Pipeline complete — ${receipt.nodeResults.length} nodes executed',
            ),
          ),
        );
      }
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Execution failed: $e')),
      );
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Node Card — Draggable capability widget on the canvas
// ═══════════════════════════════════════════════════════════════════════════════

class _NodeCard extends StatelessWidget {
  final PipelineNode node;
  final bool isSelected;
  final VoidCallback onTap;
  final ValueChanged<Offset> onDrag;
  final VoidCallback onDelete;

  const _NodeCard({
    required this.node,
    required this.isSelected,
    required this.onTap,
    required this.onDrag,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final stateColor = switch (node.state) {
      NodeExecutionState.idle => null,
      NodeExecutionState.queued => Colors.orange,
      NodeExecutionState.running => Colors.blue,
      NodeExecutionState.success => Colors.green,
      NodeExecutionState.failed => Colors.red,
    };

    return GestureDetector(
      onTap: onTap,
      onPanUpdate: (details) => onDrag(details.delta),
      child: Container(
        width: 220,
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected
                ? theme.colorScheme.primary
                : stateColor ?? theme.colorScheme.outlineVariant,
            width: isSelected ? 2 : 1,
          ),
          boxShadow: [
            if (isSelected)
              BoxShadow(
                color: theme.colorScheme.primary.withAlpha(40),
                blurRadius: 8,
                spreadRadius: 1,
              ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            // Header
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHigh,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(11)),
              ),
              child: Row(
                children: [
                  Icon(Icons.menu, size: 14, color: theme.colorScheme.onSurfaceVariant),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      node.label,
                      style: theme.textTheme.labelMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (stateColor != null)
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: stateColor,
                        shape: BoxShape.circle,
                      ),
                    ),
                  const SizedBox(width: 4),
                  InkWell(
                    onTap: onDelete,
                    child: Icon(Icons.close, size: 14,
                        color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            // Body
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Capability ID
                  Text(
                    node.capability.id.isNotEmpty
                        ? node.capability.id
                        : node.capability.productId,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                      fontFamily: 'monospace',
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  // Price
                  Row(
                    children: [
                      Icon(Icons.attach_money, size: 14,
                          color: theme.colorScheme.primary),
                      Text(
                        '\$${node.capability.pricePerCallUsd.toStringAsFixed(2)}/call',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.primary,
                        ),
                      ),
                      const Spacer(),
                      // Version
                      Text(
                        'v${node.capability.version}',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                  if (node.cachedOutput != null) ...[
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: Colors.green.withAlpha(15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.check_circle, size: 12, color: Colors.green),
                          const SizedBox(width: 4),
                          Text('Output cached',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: Colors.green,
                              )),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            // Port indicators
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHigh,
                borderRadius: const BorderRadius.vertical(bottom: Radius.circular(11)),
              ),
              child: Row(
                children: [
                  // Input port
                  Icon(Icons.input, size: 12,
                      color: theme.colorScheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Text('in', style: theme.textTheme.labelSmall),
                  const Spacer(),
                  Text('out', style: theme.textTheme.labelSmall),
                  const SizedBox(width: 4),
                  Icon(Icons.output, size: 12,
                      color: theme.colorScheme.onSurfaceVariant),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Edge Painter — Draws bezier curves between connected nodes
// ═══════════════════════════════════════════════════════════════════════════════

class _EdgePainter extends CustomPainter {
  final PipelineDag pipeline;
  final Color color;

  _EdgePainter({required this.pipeline, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withAlpha(100)
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;

    final nodeMap = {for (final n in pipeline.nodes) n.id: n};

    for (final edge in pipeline.edges) {
      final source = nodeMap[edge.sourceNodeId];
      final target = nodeMap[edge.targetNodeId];
      if (source == null || target == null) continue;

      // Connection points: right edge of source, left edge of target
      final startX = source.position.dx + 220;
      final startY = source.position.dy + 60;
      final endX = target.position.dx;
      final endY = target.position.dy + 60;

      final controlPointOffset = (endX - startX).abs() * 0.4;
      final controlX1 = startX + controlPointOffset;
      final controlX2 = endX - controlPointOffset;

      final path = Path()
        ..moveTo(startX, startY)
        ..cubicTo(controlX1, startY, controlX2, endY, endX, endY);

      canvas.drawPath(path, paint);

      // Arrow head
      final arrowSize = 6.0;
      final angle = atan2(endY - controlX2, endX - controlX2); // approximate tangent
      final arrowPaint = Paint()
        ..color = color.withAlpha(150)
        ..style = PaintingStyle.fill;

      final arrowPath = Path()
        ..moveTo(endX, endY)
        ..lineTo(
          endX - arrowSize * cos(angle - 0.5),
          endY - arrowSize * sin(angle - 0.5),
        )
        ..lineTo(
          endX - arrowSize * cos(angle + 0.5),
          endY - arrowSize * sin(angle + 0.5),
        )
        ..close();

      canvas.drawPath(arrowPath, arrowPaint);
    }
  }

  @override
  bool shouldRepaint(_EdgePainter old) => true;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Capability Browser — Search and discover marketplace capabilities
// ═══════════════════════════════════════════════════════════════════════════════

class CapabilityBrowser extends StatefulWidget {
  const CapabilityBrowser({super.key});

  @override
  State<CapabilityBrowser> createState() => _CapabilityBrowserState();
}

class _CapabilityBrowserState extends State<CapabilityBrowser> {
  final _searchController = TextEditingController();
  String? _selectedCategory;

  static const _categories = [
    null,
    'career',
    'developer-tools',
    'security',
    'devops',
    'marketing',
    'productivity',
  ];

  static const _categoryLabels = {
    null: 'All Categories',
    'career': 'Career',
    'developer-tools': 'Developer Tools',
    'security': 'Security',
    'devops': 'DevOps',
    'marketing': 'Marketing',
    'productivity': 'Productivity',
  };

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PipelineState>(
      builder: (context, state, _) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('Discover Capabilities'),
            actions: [
              if (!state.connected)
                TextButton.icon(
                  icon: const Icon(Icons.link),
                  label: const Text('Connect to search'),
                  onPressed: () => _showQuickConnectDialog(context),
                ),
            ],
          ),
          body: Column(
            children: [
              // Search bar
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _searchController,
                        decoration: InputDecoration(
                          hintText: 'Search by intent...',
                          prefixIcon: const Icon(Icons.search),
                          suffixIcon: state.discovering
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: Padding(
                                    padding: EdgeInsets.all(12),
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  ),
                                )
                              : IconButton(
                                  icon: const Icon(Icons.send),
                                  onPressed: state.connected
                                      ? () => _search(state)
                                      : null,
                                ),
                          border: const OutlineInputBorder(),
                        ),
                        onSubmitted: (_) => _search(state),
                      ),
                    ),
                    const SizedBox(width: 12),
                    DropdownButton<String?>(
                      value: _selectedCategory,
                      items: _categories.map((c) {
                        return DropdownMenuItem(
                          value: c,
                          child: Text(_categoryLabels[c] ?? ''),
                        );
                      }).toList(),
                      onChanged: (v) => setState(() => _selectedCategory = v),
                    ),
                  ],
                ),
              ),

              // Results
              Expanded(
                child: state.discoveryError != null
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.error_outline, size: 48),
                            const SizedBox(height: 16),
                            Text('Discovery Error',
                                style: Theme.of(context).textTheme.titleMedium),
                            Text(state.discoveryError!),
                          ],
                        ),
                      )
                    : state.discoveredCaps.isEmpty
                        ? Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.search_off, size: 64,
                                    color: Theme.of(context).colorScheme.outline),
                                const SizedBox(height: 16),
                                Text('No capabilities found',
                                    style: Theme.of(context).textTheme.titleMedium),
                                const SizedBox(height: 8),
                                Text(
                                  'Connect to a hub and search by intent to discover\nmarketplace capabilities for your pipeline.',
                                  textAlign: TextAlign.center,
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.symmetric(horizontal: 16),
                            itemCount: state.discoveredCaps.length,
                            itemBuilder: (context, index) {
                              final cap = state.discoveredCaps[index];
                              return _CapabilityCard(
                                capability: cap,
                                onAddToCanvas: () {
                                  if (state.activePipeline == null) {
                                    state.createPipeline(
                                        'Pipeline from ${cap.name}');
                                  }
                                  state.addNode(cap, Offset(100, 100));
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                          'Added "${cap.name}" to pipeline'),
                                      duration: const Duration(seconds: 1),
                                    ),
                                  );
                                },
                              );
                            },
                          ),
              ),
            ],
          ),
        );
      },
    );
  }

  void _search(PipelineState state) {
    final intent = _searchController.text.trim();
    if (intent.isEmpty || !state.connected) return;
    state.discoverCapabilities(
      intent: intent,
      category: _selectedCategory,
    );
  }

  void _showQuickConnectDialog(BuildContext context) {
    final keyController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Connect Wallet'),
        content: TextField(
          controller: keyController,
          obscureText: true,
          decoration: const InputDecoration(
            labelText: 'Wallet Private Key',
            hintText: 'Enter your wallet key',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              context.read<PipelineState>().connect(keyController.text.trim());
              Navigator.of(ctx).pop();
            },
            child: const Text('Connect'),
          ),
        ],
      ),
    );
  }
}

/// A single capability card in the search results.
class _CapabilityCard extends StatelessWidget {
  final Capability capability;
  final VoidCallback onAddToCanvas;

  const _CapabilityCard({
    required this.capability,
    required this.onAddToCanvas,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(capability.name,
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      )),
                  const SizedBox(height: 4),
                  Text(capability.description,
                      style: theme.textTheme.bodySmall,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    children: [
                      _InfoChip(
                        icon: Icons.attach_money,
                        label: '\$${capability.pricePerCallUsd.toStringAsFixed(2)}',
                      ),
                      if (capability.version.isNotEmpty)
                        _InfoChip(
                          icon: Icons.tag,
                          label: 'v${capability.version}',
                        ),
                      if (capability.p50LatencyMs != null)
                        _InfoChip(
                          icon: Icons.timer_outlined,
                          label: '${capability.p50LatencyMs!.round()}ms',
                        ),
                      if (capability.trustScore != null)
                        _InfoChip(
                          icon: Icons.verified,
                          label: '${(capability.trustScore! * 100).round()}%',
                        ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            FilledButton.tonalIcon(
              onPressed: onAddToCanvas,
              icon: const Icon(Icons.add, size: 16),
              label: const Text('Add'),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  final IconData icon;
  final String label;

  const _InfoChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: Theme.of(context).colorScheme.onSurfaceVariant),
        const SizedBox(width: 2),
        Text(label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                )),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Templates Marketplace — Browse and purchase published pipeline templates
// ═══════════════════════════════════════════════════════════════════════════════

class TemplatesMarketplace extends StatelessWidget {
  const TemplatesMarketplace({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // Sample template data for the UI concept
    final templates = [
      _TemplateInfo(
        name: 'LinkedIn -> Email -> CRM',
        description: 'Analyze a LinkedIn profile, generate a personalized cold email, and log the contact to your CRM.',
        author: 'alex@example.com',
        price: 4.99,
        nodeCount: 3,
        category: 'career',
        rating: 4.5,
        purchases: 128,
      ),
      _TemplateInfo(
        name: 'Code Review -> Security -> Deploy',
        description: 'Automated PR quality gate: code review, vulnerability scanning, and deployment readiness check.',
        author: 'devops@example.com',
        price: 9.99,
        nodeCount: 3,
        category: 'developer-tools',
        rating: 4.8,
        purchases: 89,
      ),
      _TemplateInfo(
        name: 'Trend Detection -> Content -> Schedule',
        description: 'Daily content pipeline that detects trends, generates posts, and queues them for social media.',
        author: 'marketer@example.com',
        price: 6.99,
        nodeCount: 4,
        category: 'marketing',
        rating: 4.2,
        purchases: 56,
      ),
      _TemplateInfo(
        name: 'Resume Parsing -> ATS Scoring -> Report',
        description: 'Parse candidate resumes, score against ATS rules for fintech roles, and generate a detailed report.',
        author: 'recruiter@example.com',
        price: 3.99,
        nodeCount: 3,
        category: 'career',
        rating: 4.6,
        purchases: 203,
      ),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pipeline Templates'),
        actions: [
          IconButton(
            icon: const Icon(Icons.filter_list),
            tooltip: 'Filter',
            onPressed: () {},
          ),
        ],
      ),
      body: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: templates.length,
        itemBuilder: (context, index) {
          final t = templates[index];
          return Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(t.name,
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                            )),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primaryContainer,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(t.category,
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: theme.colorScheme.onPrimaryContainer,
                            )),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(t.description,
                      style: theme.textTheme.bodySmall,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      _InfoChip(icon: Icons.person_outline, label: t.author),
                      const SizedBox(width: 16),
                      _InfoChip(
                          icon: Icons.account_tree,
                          label: '${t.nodeCount} nodes'),
                      const SizedBox(width: 16),
                      _InfoChip(
                          icon: Icons.star_half,
                          label: '${t.rating} (${t.purchases})'),
                      const Spacer(),
                      Text('\$${t.price.toStringAsFixed(2)}',
                          style: theme.textTheme.titleSmall?.copyWith(
                            color: theme.colorScheme.primary,
                            fontWeight: FontWeight.w700,
                          )),
                      const SizedBox(width: 12),
                      FilledButton.tonal(
                        onPressed: () {
                          final state = context.read<PipelineState>();
                          state.createPipeline(t.name);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                  'Cloned template "${t.name}" — customize it on the Canvas'),
                            ),
                          );
                        },
                        child: const Text('Clone'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Internal data class for template marketplace display.
class _TemplateInfo {
  final String name;
  final String description;
  final String author;
  final double price;
  final int nodeCount;
  final String category;
  final double rating;
  final int purchases;

  const _TemplateInfo({
    required this.name,
    required this.description,
    required this.author,
    required this.price,
    required this.nodeCount,
    required this.category,
    required this.rating,
    required this.purchases,
  });
}
