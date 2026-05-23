# Pipeline Composer Architecture

## Overview

Capability Composer is a desktop application that implements a **visual node-graph pipeline editor** on top of the AI Market Protocol. Users discover marketplace capabilities, chain them into pipelines, execute those pipelines, and optionally publish the pipeline as a purchasable template.

```
┌──────────────────────────────────────────────────────────┐
│                    Capability Composer                     │
│                                                           │
│  ┌────────────────────┐   ┌──────────────────────────┐   │
│  │   Pipeline Canvas   │   │   Capability Browser     │   │
│  │  (Node Graph Editor)│   │   (Search + Filter)      │   │
│  │                     │   │                          │   │
│  │  [Node]───[Node]    │   │  ┌─ Intent search ──┐   │   │
│  │       \            │   │  ├─ Category filter  │   │   │
│  │        [Node]      │   │  ├─ Price range      │   │   │
│  │                     │   │  └─ Trust score      │   │   │
│  └─────────┬───────────┘   └──────────┬───────────┘   │
│            │                          │                │
│  ┌─────────┴──────────────────────────┴───────────┐   │
│  │           Pipeline Graph Model                   │   │
│  │  (DAG of CapabilityNodes + Edges + State)       │   │
│  └─────────────────────┬───────────────────────────┘   │
│                        │                                │
│  ┌─────────────────────┴───────────────────────────┐   │
│  │         Pipeline Execution Engine                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐   │   │
│  │  │ Topological│ │Parallel  │ │Payment Channel│   │   │
│  │  │ Sorter    │ │ Executor │ │  Manager      │   │   │
│  │  └──────────┘ └──────────┘ └────────────────┘   │   │
│  └─────────────────────┬───────────────────────────┘   │
│                        │                                │
│  ┌─────────────────────┴───────────────────────────┐   │
│  │          aimarket_agent Dart SDK                 │   │
│  │  Discover | OpenChannel | Invoke | Settle       │   │
│  └─────────────────────┬───────────────────────────┘   │
└────────────────────────┼──────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │   AI Market Hub     │
              │  (hub.aicom.io)     │
              └─────────────────────┘
```

---

## Component Architecture

### 1. Pipeline Graph Model

The core data structure is a **directed acyclic graph (DAG)** of capability nodes connected by data flow edges.

#### PipelineDag

```dart
class PipelineDag {
  final String id;
  final String name;
  final String description;
  final List<PipelineNode> nodes;
  final List<DataEdge> edges;
  final Map<String, dynamic> metadata;
}
```

#### PipelineNode

```dart
class PipelineNode {
  final String id;
  final Capability capability;      // From marketplace discovery
  final Offset position;            // Canvas position
  final Map<String, String> inputMappings;  // Edge source -> input field
  final NodeExecutionState state;   // idle | queued | running | done | failed
  Map<String, dynamic>? cachedOutput;
  double? actualCostUsd;
  double? actualLatencyMs;
}
```

#### DataEdge

```dart
class DataEdge {
  final String id;
  final String sourceNodeId;
  final String sourceField;         // Which output field
  final String targetNodeId;
  final String targetField;         // Which input field
  final ValueTransformer? transform; // Optional transformation
}
```

### 2. Capability Discovery Service

Wraps the aimarket_agent `discover()` method with caching, filtering, and comparison.

```
search(intent, {category, maxBudget, minTrustScore, maxLatencyMs})
  -> List<CapabilityMatch>
     each match has: capability, relevanceScore, rationale, estimatedTotalCost
```

Key behaviors:
- **Intent expansion**: automatically generates related search terms
- **Multi-category search**: when a pipeline needs capabilities across categories
- **Schema comparison**: highlights compatible output/input ports between capabilities
- **Cost estimation**: computes pipeline-wide cost including per-node invocation fees

### 3. Node Graph Editor

The visual canvas is implemented using Flutter's `CustomPainter` for the graph and a composable widget tree for the node UI.

**Rendering layers** (bottom to top):
1. **Grid** — infinite scrollable grid with snap points
2. **Edges** — bezier curves rendered with `CustomPainter`
3. **Nodes** — draggable cards showing capability name, status, ports
4. **Selection overlay** — multi-select marquee
5. **Minimap** — overview of the entire pipeline in the corner
6. **Context menu** — right-click actions per node

**Interaction model:**
- Drag node title bar to move
- Drag from output port to input port to create edge
- Click to select, Shift+click to multi-select
- Delete key removes selected nodes/edges
- Double-click node to configure input mappings

### 4. Pipeline Execution Engine

Executes a `PipelineDag` against the marketplace.

#### Phase 1: Topological Sort

Computes execution order respecting data dependencies. Parallel branches are identified for concurrent execution.

```dart
List<ExecutionBatch> topoSort(PipelineDag dag)
  // Returns batches of nodes that can execute in parallel
```

#### Phase 2: Channel Estimation

Computes the total cost across all nodes and opens a single payment channel with sufficient deposit.

```dart
Future<Channel> openChannelForPipeline(PipelineDag dag)
  totalCost = sum of all node.pricePerCallUsd
  return agent.openChannel(totalCost * 1.2)  // 20% buffer
```

#### Phase 3: Step-by-Step Execution

Executes each batch, passing outputs as inputs downstream.

```dart
Future<PipelineResult> execute(
  PipelineDag dag,
  Channel channel,
  Map<String, dynamic> pipelineInput,
) async {
  for (batch in topoSort(dag)) {
    final futures = batch.map((node) => executeNode(node, channel));
    final results = await Future.wait(futures);
    // Wire outputs to downstream node inputs
    for (edge in edgesFrom(batch)) {
      downstreamInput[edge.targetField] = results[edge.sourceNodeId][edge.sourceField];
    }
  }
}
```

#### Phase 4: Settlement

Closes the channel and records the final bill of materials.

```dart
Future<PipelineReceipt> settle(PipelineDag dag, Channel channel)
```

### 5. Pipeline Template Marketplace

Users can publish their pipelines as purchasable templates.

**Publishing flow:**
1. User completes a pipeline and verifies it works
2. App calls `POST /ai-market/v2/product/publish` with:
   - Pipeline DAG serialization
   - Price for the template
   - Category, tags, description
   - Attribution to upstream capability sellers
3. Hub creates a product page for the pipeline template
4. Other users can buy the template and clone it into their own workspace

**Buying flow:**
1. Browse pipeline templates in the marketplace browser
2. Purchase template (one-time fee or per-execution)
3. Template DAG is cloned into the user's workspace
4. User can customize nodes, add/remove capabilities
5. User funds their own payment channels for execution

---

## Pipeline Serialization Format

Pipelines are serialized as JSON for storage, sharing, and marketplace distribution.

```json
{
  "format_version": "1.0",
  "pipeline": {
    "id": "pl_abc123",
    "name": "LinkedIn -> Email -> CRM",
    "description": "Analyze a LinkedIn profile, generate a cold email, log to CRM",
    "version": "2.1.0",
    "author": "alex@example.com",
    "created_at": "2026-05-23T10:00:00Z",
    "updated_at": "2026-05-23T12:30:00Z",
    "tags": ["recruiting", "outreach", "crm", "career"],
    "category": "career",
    "price_usd": 4.99
  },
  "nodes": [
    {
      "id": "node_1",
      "capability_id": "linkedin-proxy-v3",
      "product_id": "linkedin-proxy-enterprise",
      "source_hub": "https://hub.aicom.io",
      "name": "LinkedIn Profile Analysis",
      "position": { "x": 100, "y": 200 },
      "input_mappings": {
        "profile_url": "pipeline_input.profile_url"
      },
      "default_input": {
        "include_publications": true,
        "include_recommendations": false
      }
    },
    {
      "id": "node_2",
      "capability_id": "cold-email-gen-v2",
      "product_id": "cold-email-pro",
      "source_hub": "https://hub.aicom.io",
      "name": "Cold Email Generation",
      "position": { "x": 450, "y": 200 },
      "input_mappings": {
        "target_name": "node_1.output.name",
        "target_role": "node_1.output.current_role",
        "target_company": "node_1.output.current_company",
        "profile_summary": "node_1.output.summary"
      },
      "default_input": {
        "tone": "professional",
        "max_length": 200
      }
    },
    {
      "id": "node_3",
      "capability_id": "crm-contact-create-v1",
      "product_id": "crm-sync-hubspot",
      "source_hub": "https://hub.aicom.io",
      "name": "CRM Contact Creation",
      "position": { "x": 800, "y": 200 },
      "input_mappings": {
        "contact_name": "node_1.output.name",
        "contact_email": "node_2.output.suggested_email",
        "notes": "node_2.output.email_body"
      },
      "default_input": {
        "crm_system": "hubspot",
        "add_to_list": "Outreach Q2 2026"
      }
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source_node": "node_1",
      "source_field": "output",
      "target_node": "node_2",
      "target_field": "input"
    },
    {
      "id": "edge_2",
      "source_node": "node_1",
      "source_field": "output",
      "target_node": "node_3",
      "target_field": "input"
    },
    {
      "id": "edge_3",
      "source_node": "node_2",
      "source_field": "output",
      "target_node": "node_3",
      "target_field": "input"
    }
  ],
  "execution_config": {
    "max_concurrency": 2,
    "retry_on_failure": true,
    "max_retries": 3,
    "timeout_per_node_s": 60,
    "tee_required": false
  }
}
```

---

## Key Design Decisions

### Why a DAG instead of sequential steps?
Capabilities have diverse input/output schemas. A DAG captures complex branching, parallel execution, and fan-out/fan-in patterns that sequential steps cannot.

### Why a local execution engine instead of server-side?
User data (LinkedIn profiles, emails, CRM data) never leaves the desktop app except through attested TEE capabilities. Privacy-first architecture.

### Why pre-funded channels instead of per-call payment?
Pipeline execution involves multiple rapid invocations. A single pre-funded channel avoids per-call transaction overhead and enables sub-second switching between capabilities.

### Why pipeline templates as marketplace products?
Pipelines are more valuable than individual capabilities. Templates create a new asset class in the marketplace and give capability sellers additional distribution through pipeline creators.
