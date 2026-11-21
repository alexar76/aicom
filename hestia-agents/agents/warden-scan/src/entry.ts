// The HESTIA agent warden.scan@v1: WARDEN's static scan of MCP tool definitions, as a
// callable check. Built into ../handler.js by hestia-agents/scripts/build_warden_scan.sh.
import { StaticScanGate, staticScanRulesetRef } from "../../../../warden/src/static-scan.ts";
import { tryCanonicalToolsHash } from "../../../../warden/src/pinning.ts";
import { hintContradictionFindings } from "../../../../warden/src/hint-claims.ts";
import type { Severity, ToolDef, WardenFinding } from "../../../../warden/src/types.ts";

declare const WARDEN_VERSION: string;

const SEVERITIES: Severity[] = ["info", "low", "medium", "high", "critical"];
const MAX_TOOLS = 500;

function toolsFrom(payload: Record<string, unknown>): ToolDef[] {
  let tools = payload.tools;
  if (tools && !Array.isArray(tools) && typeof tools === "object" && Array.isArray((tools as { tools?: unknown }).tools)) {
    tools = (tools as { tools: unknown[] }).tools; // a whole tools/list result
  }
  if (!Array.isArray(tools) || tools.length === 0) {
    throw new Error("send tools: the MCP tools/list array (or the whole result object that holds it)");
  }
  if (tools.length > MAX_TOOLS) throw new Error(`at most ${MAX_TOOLS} tools per call`);
  return tools.map((tool, i) => {
    if (!tool || typeof tool !== "object" || Array.isArray(tool)) throw new Error(`tools[${i}] is not an object`);
    const name = (tool as { name?: unknown }).name;
    if (typeof name !== "string" || !name) throw new Error(`tools[${i}] has no name`);
    return tool as ToolDef;
  });
}

export async function handle(payload: Record<string, unknown>) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("send an object with tools");
  const tools = toolsFrom(payload);
  const blockAt = (payload.block_at ?? "high") as Severity;
  if (!SEVERITIES.includes(blockAt)) throw new Error("block_at must be one of " + SEVERITIES.join(", "));
  const gate = new StaticScanGate();
  const result = await gate.evaluate({
    server: { id: "hestia-call" } as never,
    tools,
    prior: [],
    policy: { blockAtSeverity: blockAt } as never,
  });
  const rank = (s: Severity) => SEVERITIES.indexOf(s);
  // As `warden scan` does: the static rules, plus hints the tool's own description contradicts
  // (advisory: reported, never blocking).
  const all = [...result.findings, ...hintContradictionFindings(tools)];
  const findings = all.map((f: WardenFinding) => ({
    tool: f.tool ?? null, code: f.code, severity: f.severity, message: f.message,
    advisory: f.advisory === true,
  }));
  const worst = findings.reduce<Severity | null>((w, f) => (w === null || rank(f.severity) > rank(w) ? f.severity : w), null);
  // An advisory finding is reported and never blocks, at any threshold (WardenFinding.advisory).
  const blocking = findings.filter((f) => !f.advisory && rank(f.severity) >= rank(blockAt));
  const toolsHash = tryCanonicalToolsHash(tools);
  return {
    verdict: blocking.length ? "block" : "allow",
    block_at: blockAt,
    worst_severity: worst,
    findings,
    tools_checked: tools.length,
    tools_sha256: toolsHash ?? null,
    tools_sha256_note: toolsHash ? "RFC 8785 digest of the set, the form HISTOR records" :
      "no canonical digest: the set has a non-integer number (RFC 8785 in WARDEN refuses those)",
    ruleset: result.ruleset ?? staticScanRulesetRef(),
    warden: WARDEN_VERSION,
    scope: "static rules over names, descriptions, schemas and metadata; no model, no network, " +
      "no running of the server",
  };
}
