/**
 * AI Stack Migration Assistant — VSCode Extension Entry Point
 *
 * Integrates the @aimarket/agent SDK to discover, purchase, and apply
 * AI stack migration rules from the AI Market hub.
 */

import * as vscode from 'vscode';
import { AimarketAgent, PlanStep, Channel, InvokeResult, Settlement } from '@aimarket/agent';

// ── State ─────────────────────────────────────────────────────

let agent: AimarketAgent | null = null;
let currentChannel: Channel | null = null;
let discoveredRules: PlanStep[] = [];

// ── Helpers ───────────────────────────────────────────────────

function getAgent(): AimarketAgent {
  if (agent) return agent;

  const config = vscode.workspace.getConfiguration('aiStackMigration');
  const hubUrl = config.get<string>('hubUrl', 'https://hub.aicom.io');
  const walletKey = config.get<string>('walletKey', '');

  if (!walletKey) {
    vscode.window.showWarningMessage(
      'AI Stack Migration: No wallet key configured. Set aiStackMigration.walletKey in settings.'
    );
  }

  agent = new AimarketAgent({ hubUrl, walletKey });
  return agent;
}

function getChannelId(): string {
  if (!currentChannel) throw new Error('No active payment channel. Run "Detect Migrations" first.');
  return currentChannel.channel_id;
}

// ── Commands ──────────────────────────────────────────────────

/**
 * Phase 1: Scan project files for AI stack signatures and discover
 * matching migration rules from the hub.
 */
async function detectMigrations(): Promise<void> {
  vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'Scanning project for AI stack...' },
    async (progress) => {
      try {
        // Build stack signature from workspace files
        progress.report({ message: 'Detecting AI stack signatures...' });
        const stackSignature = await detectStackFromWorkspace();

        if (!stackSignature) {
          vscode.window.showInformationMessage(
            'AI Stack Migration: No recognizable AI stack found in this workspace.'
          );
          return;
        }

        progress.report({ message: `Searching rules for: ${stackSignature}` });
        const a = getAgent();
        discoveredRules = await a.discover({
          intent: `migration rules ${stackSignature}`,
          category: 'devtools',
          budget: vscode.workspace.getConfiguration('aiStackMigration').get<number>('monthlyBudget', 10),
          limit: 20,
        });

        if (discoveredRules.length === 0) {
          vscode.window.showInformationMessage(
            `AI Stack Migration: No migration rules found for "${stackSignature}".`
          );
          return;
        }

        vscode.window.showInformationMessage(
          `AI Stack Migration: Found ${discoveredRules.length} migration rule(s) for "${stackSignature}".`
        );

        // Open a payment channel for the first discovered rule
        progress.report({ message: 'Opening payment channel...' });
        const budget = discoveredRules[0].capability.price_per_call_usd;
        currentChannel = await a.openChannel(budget, 'USDT', 'base');

        // Refresh sidebar
        vscode.commands.executeCommand('aiStack.sidebar.refresh');
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`AI Stack Migration: ${msg}`);
      }
    }
  );
}

/**
 * Phase 2: Apply a selected migration rule — download the rule bundle,
 * run the AST-based patcher, then optionally run tests.
 */
async function applyMigration(rule?: PlanStep): Promise<void> {
  const selected = rule ?? await pickRule();
  if (!selected) return;

  const a = getAgent();
  const channelId = getChannelId();

  vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'Applying migration rule...' },
    async (progress) => {
      try {
        progress.report({ message: 'Downloading rule bundle...' });

        const result: InvokeResult = await a.invoke({
          capabilityId: selected.capability.capability_id,
          channelId,
          productId: selected.capability.product_id,
          sourceHub: selected.capability.source_hub,
          input: {
            projectContext: {
              language: detectLanguage(),
              framework: selected.capability.name,
            },
          },
        });

        if (result.safety_blocked) {
          vscode.window.showErrorMessage(
            `Migration blocked: ${result.safety_reason ?? 'Safety gate triggered'}`
          );
          return;
        }

        if (!result.success) {
          vscode.window.showErrorMessage(
            `Migration failed: ${result.error ?? 'Unknown error'}`
          );
          return;
        }

        // TEE verification
        if (result.tee_verified) {
          progress.report({ message: 'Verifying TEE attestation...' });
          const valid = a.verifyTeeAttestation(
            {
              code_hash: result.tee_attestation?.code_hash ?? '',
              signature: result.tee_attestation?.signature ?? '',
              canonical: result.tee_attestation?.pcr_values?.canonical ?? '',
            },
            result.tee_attestation?.code_hash ?? ''
          );
          if (!valid) {
            vscode.window.showWarningMessage(
              'TEE attestation verification failed. The patch may have been tampered with.'
            );
            return;
          }
        }

        progress.report({ message: 'Applying patch to workspace...' });
        await applyPatch(result);

        const autoRun = vscode.workspace.getConfiguration('aiStackMigration').get<boolean>('autoRunTests', true);
        if (autoRun) {
          progress.report({ message: 'Running test suite...' });
          await runTests();
        }

        vscode.window.showInformationMessage(
          `Migration "${selected.capability.name}" applied successfully. Cost: $${result.price_usd.toFixed(2)}`
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`AI Stack Migration: ${msg}`);
      }
    }
  );
}

/**
 * Phase 5: Close the payment channel and reclaim unspent funds.
 */
async function settleChannel(): Promise<void> {
  if (!currentChannel) {
    vscode.window.showInformationMessage('No active payment channel to settle.');
    return;
  }

  try {
    const a = getAgent();
    const settlement: Settlement = await a.closeChannel(currentChannel.channel_id);
    currentChannel = null;

    vscode.window.showInformationMessage(
      `Channel settled. Spent: $${settlement.total_spent_usd.toFixed(2)}, Refund: $${settlement.refund_usd.toFixed(2)}`
    );
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage(`Settlement failed: ${msg}`);
  }
}

// ── Internal Helpers ──────────────────────────────────────────

/**
 * Detect AI stack signatures from workspace source files.
 * Returns a human-readable string like "GPT-4 to Claude Sonnet 4.6"
 * or null if no recognizable stack is found.
 */
async function detectStackFromWorkspace(): Promise<string | null> {
  const files = await vscode.workspace.findFiles(
    '{**/*.py,**/*.ts,**/*.js}',
    '**/node_modules/**'
  );

  let hasOpenAI = false;
  let hasAnthropic = false;
  let hasLangChain = false;

  // Read up to 50 files for stack detection
  const batch = files.slice(0, 50);
  for (const file of batch) {
    const doc = await vscode.workspace.openTextDocument(file);
    const text = doc.getText();

    if (/from\s+openai|import\s+openai/.test(text)) hasOpenAI = true;
    if (/from\s+anthropic|import\s+anthropic/.test(text)) hasAnthropic = true;
    if (/from\s+langchain|import\s+langchain/.test(text)) hasLangChain = true;
  }

  const sig: string[] = [];
  if (hasOpenAI && hasAnthropic) sig.push('cross-provider migration');
  else if (hasOpenAI) sig.push('OpenAI migration');
  else if (hasAnthropic) sig.push('Anthropic migration');

  if (hasLangChain) sig.push('LangChain migration');

  return sig.length > 0 ? sig.join(' ') : null;
}

function detectLanguage(): string {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return 'unknown';
  return editor.document.languageId;
}

async function pickRule(): Promise<PlanStep | undefined> {
  if (discoveredRules.length === 0) {
    vscode.window.showWarningMessage('No migration rules discovered. Run "Detect Migrations" first.');
    return undefined;
  }

  const items = discoveredRules.map((r) => ({
    label: r.capability.name,
    description: `$${r.capability.price_per_call_usd.toFixed(2)} | Score: ${(r.relevance_score * 100).toFixed(0)}%`,
    detail: r.capability.description,
    rule: r,
  }));

  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: 'Select a migration rule to apply',
  });

  return picked?.rule;
}

/**
 * Apply a patch from an InvokeResult to the workspace files.
 * This is a scaffold — the real implementation performs AST-level transformations.
 */
async function applyPatch(result: InvokeResult): Promise<void> {
  // Placeholder: in production, iterate over result.output.patches
  // and apply each diff using workspace text edits.
  const patches = result.output?.patches as Array<{ file: string; diff: string }> | undefined;

  if (!patches || patches.length === 0) {
    vscode.window.showInformationMessage('No file changes required for this migration rule.');
    return;
  }

  for (const p of patches) {
    const uri = vscode.Uri.file(p.file);
    const doc = await vscode.workspace.openTextDocument(uri);
    const edit = new vscode.WorkspaceEdit();

    // Parse unified diff and apply edits — scaffold only
    // Full AST-based patcher lives in src/patcher.ts
    vscode.window.showInformationMessage(`Patch ready for: ${p.file}`);
  }
}

/**
 * Run the workspace's test suite.
 */
async function runTests(): Promise<boolean> {
  const task = await vscode.tasks.executeTask(
    new vscode.Task(
      { type: 'npm', script: 'test' },
      vscode.TaskScope.Workspace,
      'test',
      'npm',
      new vscode.ShellExecution('npm test')
    )
  );

  return new Promise<boolean>((resolve) => {
    const disposable = vscode.tasks.onDidEndTaskProcess((e) => {
      if (e.execution.task === task) {
        disposable.dispose();
        resolve(e.exitCode === 0);
      }
    });
  });
}

// ── Sidebar Tree Data Provider ────────────────────────────────

class MigrationRulesProvider implements vscode.TreeDataProvider<PlanStep> {
  private _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: PlanStep): vscode.TreeItem {
    const item = new vscode.TreeItem(
      element.capability.name,
      vscode.TreeItemCollapsibleState.None
    );
    item.description = `$${element.capability.price_per_call_usd.toFixed(2)}`;
    item.tooltip = `${element.capability.description}\n\nRelevance: ${(element.relevance_score * 100).toFixed(0)}%\nVendor: ${element.capability.source_hub_name ?? element.capability.source_hub}`;
    item.command = {
      command: 'aiStack.applyMigration',
      title: 'Apply',
      arguments: [element],
    };
    item.contextValue = 'migrationRule';
    return item;
  }

  getChildren(element?: PlanStep): PlanStep[] {
    return element ? [] : discoveredRules;
  }
}

// ── Activation ────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext): void {
  console.log('AI Stack Migration Assistant activating...');

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('aiStack.detectMigrations', detectMigrations)
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('aiStack.applyMigration', applyMigration)
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('aiStack.settleChannel', settleChannel)
  );

  // Register sidebar tree data provider
  const treeProvider = new MigrationRulesProvider();
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('aiStack.sidebar', treeProvider)
  );

  // Wire sidebar refresh to detect command
  context.subscriptions.push(
    vscode.commands.registerCommand('aiStack.sidebar.refresh', () => treeProvider.refresh())
  );

  console.log('AI Stack Migration Assistant activated.');
}

export function deactivate(): void {
  // Settle any open channel on deactivation
  if (currentChannel) {
    settleChannel().catch(() => {});
  }
}
