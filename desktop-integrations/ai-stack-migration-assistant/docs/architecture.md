# Architecture

The AI Stack Migration Assistant is a VSCode/Cursor extension built in TypeScript. It follows a three-layer architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    VSCode Extension Layer                    │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │Commands  │  │Sidebar Panel │  │Status Bar / Notify   │  │
│  │(activate)│  │(TreeView)    │  │(Information display) │  │
│  └────┬─────┘  └──────┬───────┘  └──────────┬───────────┘  │
│       │               │                     │              │
│       └───────────────┼─────────────────────┘              │
│                       │                                    │
│              ┌────────▼────────┐                            │
│              │ Extension Host  │                            │
│              │ (activation.ts) │                            │
│              └────────┬────────┘                            │
├───────────────────────┼─────────────────────────────────────┤
│              Migration Engine Layer                         │
│  ┌────────────────────▼──────────────────────────────┐     │
│  │              Migration Orchestrator               │     │
│  │  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │     │
│  │  │Rule Resolver │  │AST Parser  │  │Patcher   │  │     │
│  │  │(discover +   │  │(TypeScript │  │(applies  │  │     │
│  │  │ download)    │  │ parser)    │  │patches)  │  │     │
│  │  └──────────────┘  └────────────┘  └──────────┘  │     │
│  └───────────────────────────────────────────────────┘     │
│                            │                                │
│  ┌─────────────────────────▼──────────────────────────┐    │
│  │              Verification Engine                   │    │
│  │  ┌────────────────┐  ┌────────────────────────┐    │    │
│  │  │Test Runner     │  │TEE Attestation Verifier│    │    │
│  │  │(vscode tasks)  │  │(patch integrity check) │    │    │
│  │  └────────────────┘  └────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
├───────────────────────┼─────────────────────────────────────┤
│              SDK Integration Layer                           │
│  ┌────────────────────▼──────────────────────────────┐     │
│  │         @aimarket/agent SDK                       │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────┐ ┌────────┐  │     │
│  │  │discover  │ │channel   │ │invoke│ │settle  │  │     │
│  │  │(search)  │ │(payment) │ │(buy) │ │(refund)│  │     │
│  │  └──────────┘ └──────────┘ └──────┘ └────────┘  │     │
│  └──────────────────────────────────────────────────┘     │
│                            │                                │
│                    ┌───────▼────────┐                       │
│                    │ AI Market Hub  │                       │
│                    │ (hub.aicom.io) │                       │
│                    └────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

## Layers

### 1. VSCode Extension Layer

Handles all VSCode-specific integration:

- **Commands** (`activate`): Registers `aiStack.detectMigrations`, `aiStack.applyMigration`, `aiStack.viewDiff`, `aiStack.runTests`.
- **Sidebar Panel** (`TreeDataProvider`): Displays discovered rules grouped by category (LLM, framework, embedding).
- **Status Bar**: Shows active channel balance, pending migrations.

### 2. Migration Engine Layer

The core migration logic, framework-agnostic (runs in Node.js environment):

- **Rule Resolver**: Calls `agent.discover()` to find relevant migration rules, then downloads rule bundles (JSON with AST patterns and replacement logic).
- **AST Parser**: Uses a TypeScript-compatible AST parser (e.g., `@typescript-eslint/parser`) to decompose source files into syntax trees. Migration rules provide pattern matchers that operate on AST nodes.
- **Patcher**: Applies transformations — import rewrites, method renames, parameter reordering, response type adjustments. Outputs a diff for user preview.
- **Test Runner**: Spawns `npm test` or `vscode tasks` and collects pass/fail results.
- **TEE Attestation Verifier**: Checks the `code_hash` in the TEE attestation returned by the hub against the expected rule bundle hash, ensuring the patch logic ran in a verified enclave.

### 3. SDK Integration Layer

The `@aimarket/agent` TypeScript SDK provides the consumer-side implementation of the AI Market Protocol v2:

1. **Discovery** — `agent.discover()` searches the hub for migration rules matching the user's intent.
2. **Channel** — `agent.openChannel()` opens a pre-funded payment channel.
3. **Invoke** — `agent.invoke()` purchases and downloads a migration rule bundle.
4. **Settle** — `agent.closeChannel()` reclaims unspent funds.
5. **Verify** — `agent.verifyTeeAttestation()` checks TEE signatures.

## Data Flow: End-to-End Migration

```
User clicks "Detect Migrations"
        │
        ▼
Extension scans project files for AI stack imports
        │
        ▼
Builds intent string: "migrate LangChain 0.1 to 0.2"
        │
        ▼
agent.discover({ intent, category: "devtools" })
        │
        ▼
Hub returns PlanStep[] with available rules + pricing
        │
        ▼
User selects a rule → agent.openChannel($5 USDC)
        │
        ▼
agent.invoke({ capabilityId, input, channelId })
        │
        ▼
Rule bundle downloaded → AST parser applies patterns
        │
        ▼
Diff generated → User previews → Confirms
        │
        ▼
Files patched → Test suite runs → Result reported
        │
        ▼
agent.closeChannel(channelId) → refund
```

## Data Decay Policy (Tier 3)

Migration rule bundles have a **30-day time-to-live** on the hub. After 30 days, a rule is flagged as stale and the extension re-discoveres fresh rules. This ensures users always get the latest migration patterns reflecting real production experience.

- Rule bundles include an `expires_at` timestamp.
- The extension caches rules locally for 24 hours, then re-validates.
- Stale rules are grayed out in the sidebar with a warning badge.

## TEE Verification

Every patch applied through the extension is accompanied by a TEE receipt from the hub:

```typescript
interface TeeReceipt {
  receipt_id: string;      // Unique receipt ID
  input_hash: string;       // SHA-256 of the rule bundle
  output_hash: string;      // SHA-256 of the generated patch
  signature: string;        // Ed25519 signature from the enclave
}
```

The extension verifies this receipt before presenting the diff to the user. If the signature does not match the hub's known public key, the migration is rejected with a security warning.
