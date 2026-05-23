# SDK Integration

The AI Stack Migration Assistant uses `@aimarket/agent`, the TypeScript consumer SDK for AI Market Protocol v2, for all marketplace interactions: discovery, payment channels, rule purchase, and verification.

## Installation

```bash
npm install @aimarket/agent
```

## Core Integration

### 1. Discovery: Finding Migration Rules

The extension calls `agent.discover()` to search the hub for migration rules matching the user's AI stack:

```typescript
import { AimarketAgent, PlanStep } from '@aimarket/agent';

const agent = new AimarketAgent({
  hubUrl: 'https://hub.aicom.io',
  walletKey: key,  // hex-encoded Ed25519 private key
});

// Detect AI stack from project files, then discover relevant rules
async function findMigrations(stackSignature: string): Promise<PlanStep[]> {
  const plan = await agent.discover({
    intent: `migration rules ${stackSignature}`,
    category: 'devtools',
    budget: 10.0,
    limit: 10,
  });

  return plan;
}

// Example: GPT-4 → Claude Sonnet 4.6
const rules = await findMigrations('GPT-4 to Claude Sonnet 4.6');
// rules[0].capability.name        => "GPT-4 → Claude 4 Sonnet migration"
// rules[0].capability.price_per_call_usd => 3.00
// rules[0].relevance_score        => 0.94
```

### 2. Payment Channel: Funding Rule Purchases

Before purchasing a rule, the extension opens a pre-funded payment channel:

```typescript
import { Channel } from '@aimarket/agent';

// Open a $5 channel on Base (default USDT)
const channel: Channel = await agent.openChannel(5.0, 'USDT', 'base');

console.log(channel.channel_id);   // "ch_abc123..."
console.log(channel.balance_usd);  // 5.0
console.log(channel.expires_at);   // ISO 8601 timestamp
```

### 3. Invoke: Purchasing and Downloading a Rule

Once the user selects a rule and reviews the pricing, the extension invokes the capability to download the rule bundle:

```typescript
import { InvokeResult } from '@aimarket/agent';

interface MigrationRule {
  patterns: AstPattern[];
  replacements: Replacement[];
  testCases: TestCase[];
  metadata: RuleMetadata;
}

async function purchaseRule(
  rule: PlanStep,
  channel: Channel
): Promise<MigrationRule> {
  const result: InvokeResult = await agent.invoke({
    capabilityId: rule.capability.capability_id,
    channelId: channel.channel_id,
    productId: rule.capability.product_id,
    sourceHub: rule.capability.source_hub,
    input: {
      // The hub uses the input to generate a project-specific patch
      projectContext: {
        language: 'python',
        framework: 'langchain',
        sourceVersion: '0.1.x',
        targetVersion: '0.2.x',
      },
    },
  });

  if (result.safety_blocked) {
    throw new Error(`Migration blocked: ${result.safety_reason}`);
  }

  return result.output as MigrationRule;
}
```

### 4. TEE Verification

After downloading a rule bundle, the extension verifies the TEE attestation to ensure the patch was generated in a verified enclave:

```typescript
function verifyRuleIntegrity(result: InvokeResult, expectedCodeHash: string): boolean {
  if (!result.tee_verified || !result.tee_attestation) {
    console.warn('No TEE attestation — rule integrity cannot be guaranteed');
    return false;
  }

  const isValid = agent.verifyTeeAttestation(
    {
      code_hash: result.tee_attestation.code_hash,
      signature: result.tee_attestation.signature,
      canonical: result.tee_attestation.pcr_values?.canonical ?? '',
    },
    expectedCodeHash
  );

  return isValid;
}
```

### 5. Settlement: Closing the Channel

After the migration is complete (or cancelled), the extension closes the payment channel and reclaims unspent funds:

```typescript
import { Settlement } from '@aimarket/agent';

async function closeAndRefund(channelId: string): Promise<Settlement> {
  const settlement: Settlement = await agent.closeChannel(channelId);

  console.log(`Spent: $${settlement.total_spent_usd}`);
  console.log(`Refund: $${settlement.refund_usd}`);
  console.log(`Invocations: ${settlement.invocations}`);

  return settlement;
}
```

### 6. Full Cycle: Run Once

For simple single-rule migrations, the SDK provides a `runOnce()` convenience method that executes all five phases:

```typescript
const bom = await agent.runOnce({
  intent: 'migration rules LangChain 0.1 to 0.2 Python',
  input: {
    projectContext: {
      language: 'python',
      sourceVersion: '0.1.x',
      targetVersion: '0.2.x',
    },
  },
  depositUsd: 5.0,
  category: 'devtools',
});

console.log(bom.total_spent_usd);    // 3.00
console.log(bom.results[0].success); // true
```

## Extension Integration Points

| Extension Module | SDK Usage |
|---|---|
| `src/discovery.ts` | `agent.discover()` — find rules for detected stack |
| `src/channel.ts` | `agent.openChannel()` — fund rule purchase |
| `src/migration.ts` | `agent.invoke()` — buy and download rules |
| `src/verifier.ts` | `agent.verifyTeeAttestation()` — check patch integrity |
| `src/settlement.ts` | `agent.closeChannel()` — reclaim unspent funds |

## Configuration

The SDK is configured via VSCode settings and passed to the `AimarketAgent` constructor:

```typescript
const config = vscode.workspace.getConfiguration('aiStackMigration');
const agent = new AimarketAgent({
  hubUrl: config.get<string>('hubUrl', 'https://hub.aicom.io'),
  walletKey: config.get<string>('walletKey', ''),
});
```
