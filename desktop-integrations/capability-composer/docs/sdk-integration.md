# SDK Integration Guide

Capability Composer uses the [`aimarket_agent`](https://github.com/alexar76/aimarket-sdks/tree/main/dart) Dart SDK to discover, purchase, and invoke capabilities from the AI Market Protocol marketplace.

This guide shows how the app orchestrates multiple capabilities into a pipeline execution.

---

## Agent Initialization

```dart
import 'package:aimarket_agent/aimarket_agent.dart';

final agent = AimarketAgent(
  hubUrl: 'https://hub.aicom.io',
  walletKey: walletPrivateKey,  // From secure wallet storage
  affiliate: 'capability-composer-v1',
);
```

---

## Multi-Capability Discovery

The pipeline builder discovers capabilities across multiple categories and chains them together.

```dart
Future<PipelineDag> discoverPipelineComponents() async {
  // Step 1: Discover the LinkedIn profile analyzer
  final linkedinResults = await agent.discover(
    intent: 'LinkedIn profile analysis with skills extraction',
    budget: 5.00,
    category: 'career',
    limit: 3,
  );
  final linkedinCap = linkedinResults.first.capability;

  // Step 2: Discover the cold email generator
  final emailResults = await agent.discover(
    intent: 'cold email generation from profile data',
    budget: 5.00,
    category: 'career',
    limit: 3,
  );
  final emailCap = emailResults.first.capability;

  // Step 3: Discover the CRM integration
  final crmResults = await agent.discover(
    intent: 'CRM contact creation from email outreach',
    budget: 5.00,
    category: 'productivity',
    limit: 3,
  );
  final crmCap = crmResults.first.capability;

  // Step 4: Build the pipeline graph
  return PipelineDag(
    id: uuid(),
    name: 'LinkedIn -> Email -> CRM',
    nodes: [
      PipelineNode(id: 'node_1', capability: linkedinCap, position: const Offset(100, 200)),
      PipelineNode(id: 'node_2', capability: emailCap, position: const Offset(450, 200)),
      PipelineNode(id: 'node_3', capability: crmCap, position: const Offset(800, 200)),
    ],
    edges: [
      DataEdge(id: 'edge_1', sourceNodeId: 'node_1', sourceField: 'output',
               targetNodeId: 'node_2', targetField: 'input'),
      DataEdge(id: 'edge_2', sourceNodeId: 'node_1', sourceField: 'output',
               targetNodeId: 'node_3', targetField: 'input'),
      DataEdge(id: 'edge_3', sourceNodeId: 'node_2', sourceField: 'output',
               targetNodeId: 'node_3', targetField: 'input'),
    ],
  );
}
```

---

## Schema Compatibility Checking

Before adding edges, the composer validates that the source capability's output schema is compatible with the target capability's input schema.

```dart
bool areSchemasCompatible(Capability source, Capability target) {
  if (source.outputSchema == null || target.inputSchema == null) {
    // No schema info — allow connection but warn the user
    return true;
  }

  final sourceOutputProps = source.outputSchema!['properties'] as Map<String, dynamic>? ?? {};
  final targetInputProps = target.inputSchema!['properties'] as Map<String, dynamic>? ?? {};

  // Check if any output field type matches any required input field
  final requiredInputs = (target.inputSchema!['required'] as List<dynamic>?)
          ?.map((e) => e.toString())
          .toList() ??
      [];

  for (final required in requiredInputs) {
    if (!sourceOutputProps.containsKey(required)) {
      // Check if there's a reasonable mapping
      final compatible = hasCompatibleField(sourceOutputProps, required);
      if (!compatible) return false;
    }
  }

  return true;
}

bool hasCompatibleField(Map<String, dynamic> sourceProps, String targetField) {
  // Fuzzy field matching: "target_name" matches "name", "full_name", "candidate_name"
  final normalizedTarget = targetField.toLowerCase()
      .replaceAll('_', '')
      .replaceAll('-', '');

  for (final sourceField in sourceProps.keys) {
    final normalizedSource = sourceField.toLowerCase()
        .replaceAll('_', '')
        .replaceAll('-', '');
    if (normalizedSource.contains(normalizedTarget) ||
        normalizedTarget.contains(normalizedSource)) {
      return true;
    }
  }
  return false;
}
```

---

## Pipeline Execution

The execution engine wraps the SDK's invoke cycle for each node in topological order.

```dart
class PipelineEngine {
  final AimarketAgent agent;
  late Channel _channel;

  PipelineEngine(this.agent);

  /// Open a single payment channel for the entire pipeline.
  Future<void> initialize(PipelineDag dag) async {
    final totalCost = dag.nodes.fold<double>(
      0,
      (sum, node) => sum + node.capability.pricePerCallUsd,
    );
    _channel = await agent.openChannel(
      totalCost * 1.2,  // 20% buffer for retries
      token: 'USDT',
      chain: 'base',
    );
  }

  /// Execute the pipeline and return results for each node.
  Future<Map<String, InvokeResult>> execute(
    PipelineDag dag,
    Map<String, dynamic> pipelineInput,
  ) async {
    final results = <String, InvokeResult>{};
    final topoOrder = _topologicalSort(dag);

    // Cache of node outputs for downstream resolution
    final nodeOutputs = <String, Map<String, dynamic>>{};

    for (final batch in topoOrder) {
      // Execute all nodes in this batch in parallel
      final futures = batch.map((node) async {
        // Resolve input: merge pipeline input, upstream outputs, and defaults
        final nodeInput = _resolveNodeInput(node, dag, pipelineInput, nodeOutputs);

        final result = await agent.invoke(
          capabilityId: node.capability.id,
          input: nodeInput,
          channelId: _channel.id,
          productId: node.capability.productId,
          sourceHub: node.capability.sourceHub,
          verifyTee: true,
        );

        nodeOutputs[node.id] = result.output ?? {};
        results[node.id] = result;
        return result;
      });

      await Future.wait(futures);
    }

    return results;
  }

  /// Settle the channel and get refund.
  Future<Settlement> settle() async {
    return agent.closeChannel(_channel.id);
  }

  /// Compute topological order as batches of parallel nodes.
  List<List<PipelineNode>> _topologicalSort(PipelineDag dag) {
    final inDegree = <String, int>{};
    final adjacency = <String, List<String>>{};

    for (final node in dag.nodes) {
      inDegree[node.id] = 0;
      adjacency[node.id] = [];
    }

    for (final edge in dag.edges) {
      adjacency[edge.sourceNodeId]!.add(edge.targetNodeId);
      inDegree[edge.targetNodeId] = (inDegree[edge.targetNodeId] ?? 0) + 1;
    }

    final batches = <List<PipelineNode>>[];
    final nodeMap = {for (final n in dag.nodes) n.id: n};

    while (true) {
      final ready = inDegree.entries
          .where((e) => e.value == 0)
          .map((e) => e.key)
          .toList();

      if (ready.isEmpty) break;

      batches.add(ready.map((id) => nodeMap[id]!).toList());

      for (final id in ready) {
        inDegree.remove(id);
        for (final neighbor in adjacency[id] ?? []) {
          inDegree[neighbor] = (inDegree[neighbor] ?? 1) - 1;
        }
      }
    }

    return batches;
  }

  /// Resolve input for a node by merging upstream outputs with defaults.
  Map<String, dynamic> _resolveNodeInput(
    PipelineNode node,
    PipelineDag dag,
    Map<String, dynamic> pipelineInput,
    Map<String, Map<String, dynamic>> nodeOutputs,
  ) {
    final input = <String, dynamic>{};

    // Start with defaults
    input.addAll(node.defaultInput);

    // Override with upstream outputs via edge mappings
    for (final edge in dag.edges.where((e) => e.targetNodeId == node.id)) {
      final sourceOutput = nodeOutputs[edge.sourceNodeId];
      if (sourceOutput != null) {
        if (edge.sourceField == 'output') {
          // Entire output map
          input.addAll(sourceOutput);
        } else {
          // Specific field
          input[edge.targetField] = sourceOutput[edge.sourceField];
        }
      }
    }

    // Override with pipeline-level inputs
    for (final entry in node.inputMappings.entries) {
      final pipelineKey = entry.value;
      if (pipelineKey.startsWith('pipeline_input.')) {
        final field = pipelineKey.substring('pipeline_input.'.length);
        if (pipelineInput.containsKey(field)) {
          input[entry.key] = pipelineInput[field];
        }
      }
    }

    return input;
  }
}
```

---

## Publishing a Pipeline as a Template

```dart
Future<String> publishPipelineTemplate(
  AimarketAgent agent,
  PipelineDag dag,
) async {
  // Serialize the pipeline to the standard format
  final serialized = serializePipeline(dag);

  // Calculate attribution for upstream capability sellers
  final upstreamCaps = dag.nodes.map((n) => {
    'capability_id': n.capability.id,
    'product_id': n.capability.productId,
    'source_hub': n.capability.sourceHub,
    'price_per_call': n.capability.pricePerCallUsd,
  }).toList();

  // Create the product payload
  final payload = {
    'name': dag.name,
    'description': dag.description,
    'category': 'pipeline-template',
    'tags': ['pipeline', ...dag.nodes.map((n) => n.capability.id.split('-').first)],
    'price_usd': 4.99,  // Template purchase price
    'pipeline': serialized,
    'upstream_capabilities': upstreamCaps,
    'attribution': {
      'type': 'revenue_share',
      'percentage': 0.30,  // 30% to upstream capability sellers
    },
  };

  // In production, this calls the hub's product creation endpoint:
  // POST /ai-market/v2/product/publish
  //
  // For now, publish via a custom endpoint:
  final response = await http.post(
    Uri.parse('${agent.hubUrl}/ai-market/v2/product/publish'),
    headers: {
      'Content-Type': 'application/json',
      'X-AIMarket-Affiliate': 'capability-composer-v1',
    },
    body: json.encode(payload),
  );

  if (response.statusCode != 200 && response.statusCode != 201) {
    throw Exception('Failed to publish pipeline: ${response.statusCode}');
  }

  final data = json.decode(response.body) as Map<String, dynamic>;
  return data['product_id'] as String;
}
```

---

## Cost Estimation Before Execution

```dart
class PipelineCostEstimator {
  /// Estimate the total cost of executing a pipeline.
  static PipelineCostEstimate estimate(PipelineDag dag) {
    double baseCost = 0;
    final perNode = <String, double>{};

    for (final node in dag.nodes) {
      final estimate = node.capability.pricePerCallUsd;
      perNode[node.id] = estimate;
      baseCost += estimate;
    }

    // Add estimated gas/transaction costs for channel operations
    const channelOpenFee = 0.50;  // One-time
    const channelCloseFee = 0.10; // One-time

    return PipelineCostEstimate(
      totalBaseCost: baseCost,
      channelOpenFee: channelOpenFee,
      channelCloseFee: channelCloseFee,
      totalEstimated: baseCost + channelOpenFee + channelCloseFee,
      perNodeCosts: perNode,
      currency: 'USD',
      confidenceLevel: 0.95,  // High confidence since prices are fixed
    );
  }
}

class PipelineCostEstimate {
  final double totalBaseCost;
  final double channelOpenFee;
  final double channelCloseFee;
  final double totalEstimated;
  final Map<String, double> perNodeCosts;
  final String currency;
  final double confidenceLevel;

  const PipelineCostEstimate({
    required this.totalBaseCost,
    required this.channelOpenFee,
    required this.channelCloseFee,
    required this.totalEstimated,
    required this.perNodeCosts,
    required this.currency,
    required this.confidenceLevel,
  });
}
```

---

## TEE Verification for Sensitive Pipelines

For pipelines processing sensitive data (PII, financial records, proprietary code), each node can be verified before sending data.

```dart
Future<bool> verifyPipelineSecurity(PipelineDag dag) async {
  for (final node in dag.nodes) {
    // Fetch the capability's TEE attestation from the hub
    final manifestUri = Uri.parse(
      '${node.capability.sourceHub}/ai-market/v2/capability/${node.capability.id}/manifest',
    );
    final response = await http.get(manifestUri);
    if (response.statusCode != 200) return false;

    final manifest = json.decode(response.body) as Map<String, dynamic>;
    if (manifest['tee_attestation'] == null) {
      // Non-TEE capability — warn but allow (user preference)
      continue;
    }

    final attestation = TeeAttestation.fromJson(
      manifest['tee_attestation'] as Map<String, dynamic>,
    );

    // Trust the code hash from the hub's signed manifest
    agent.trustCodeHash(node.capability.id, attestation.codeHash);

    // Verify
    final valid = agent.verifyTeeAttestation(attestation, node.capability.id);
    if (!valid) return false;
  }
  return true;
}
```

---

## Complete Pipeline Lifecycle

```dart
Future<PipelineReceipt> runPipeline(PipelineDag dag, Map<String, dynamic> input) async {
  final agent = AimarketAgent(
    hubUrl: 'https://hub.aicom.io',
    walletKey: walletKey,
  );

  try {
    // 1. Initialize — open payment channel
    final engine = PipelineEngine(agent);
    await engine.initialize(dag);

    // 2. Verify security (optional)
    await verifyPipelineSecurity(dag);

    // 3. Execute
    final results = await engine.execute(dag, input);

    // 4. Settle
    final settlement = await engine.settle();

    // 5. Build receipt
    return PipelineReceipt(
      pipelineId: dag.id,
      results: results,
      settlement: settlement,
      executedAt: DateTime.now().toUtc(),
    );
  } finally {
    agent.dispose();
  }
}
```

---

## Error Handling

```dart
class PipelineExecutionError {
  final String nodeId;
  final String capabilityName;
  final String error;
  final bool isRetryable;

  const PipelineExecutionError({
    required this.nodeId,
    required this.capabilityName,
    required this.error,
    this.isRetryable = false,
  });
}

Future<PipelineResult> executeWithRetry(
  PipelineEngine engine,
  PipelineDag dag,
  Map<String, dynamic> input, {
  int maxRetries = 3,
}) async {
  final errors = <PipelineExecutionError>[];

  for (int attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      final results = await engine.execute(dag, input);
      return PipelineResult.success(results);
    } on AimarketException catch (e) {
      if (e.message.contains('channel depleted')) {
        // Open a new channel and retry
        await engine.initialize(dag);
        continue;
      }
      errors.add(PipelineExecutionError(
        nodeId: 'unknown',
        capabilityName: 'pipeline',
        error: e.message,
        isRetryable: true,
      ));
    } on TimeoutException {
      errors.add(PipelineExecutionError(
        nodeId: 'unknown',
        capabilityName: 'pipeline',
        error: 'Execution timed out',
        isRetryable: false,
      ));
      break;
    }
  }

  return PipelineResult.failure(errors);
}
```
