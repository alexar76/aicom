import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import {
  StaticScanGate, ThreatFeed, ThreatGate, Warden, STATIC_SCAN_RULESET_VERSION,
} from "@aimarket/warden";
import { failure, inputRequired, ok } from "./a2mcp.js";

// The package does not export ./package.json, so read it next to the entry point it resolves to.
const WARDEN_VERSION = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.resolve("@aimarket/warden")), "utf8"),
).version;

const MAX_TOOLS = 500;
const MAX_TEXT = 20_000;          // per string field of one tool definition
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._\-/]{0,199}$/;

// ── histor-check ────────────────────────────────────────────────────────────────────────
// A pre-flight for an MCP server the caller is about to connect to: HISTOR's signed record of
// its tool set — when it was first pinned, whether it changed, what the pattern scan found.
// HISTOR answers only from its own observations; it never fetches the URL it is asked about,
// so this service sends nothing to the address a caller supplies.

function historCheck({ historUrl, fetchImpl, timeoutMs }) {
  const service = {
    id: "histor-check",
    methods: ["POST", "GET"],
    fields: [
      { name: "endpoint", type: "string", required: false,
        description: "https URL of the MCP server, e.g. https://mcp.example.com/mcp (send this or name)" },
      { name: "name", type: "string", required: false,
        description: "registry name of the server, e.g. io.github.owner/server (send this or endpoint)" },
    ],
  };
  service.handle = async (params, ctx) => {
    const endpoint = typeof params.endpoint === "string" ? params.endpoint.trim() : "";
    const name = typeof params.name === "string" ? params.name.trim() : "";
    if (!endpoint && !name) return [200, inputRequired(service, "send endpoint or name")];
    let query;
    if (endpoint) {
      let url;
      try { url = new URL(endpoint); } catch { url = null; }
      if (!url || url.protocol !== "https:" || endpoint.length > 2048) {
        return [400, failure(service, "bad_endpoint", "endpoint must be an https URL of at most 2048 characters")];
      }
      query = { endpoint: url.href };
    } else {
      if (!NAME_RE.test(name)) return [400, failure(service, "bad_name", "name must be a registry name like io.github.owner/server")];
      query = { name };
    }
    let res;
    try {
      res = await fetchImpl(`${historUrl}/api/v1/check`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "user-agent": "okx-a2mcp/0.1 (+https://modelmarket.dev)",
          // HISTOR gives a routing hub ten per-caller buckets under one address, keyed on an
          // opaque buyer id; ours is a hash of the caller's address, never the address itself.
          "x-aimarket-routing-hub": "okx-a2mcp",
          "x-aimarket-buyer": ctx.callerId,
        },
        body: JSON.stringify(query),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch {
      return [502, failure(service, "upstream_unreachable", "HISTOR did not answer; try again")];
    }
    if (res.status === 429) return [429, failure(service, "rate_limited", "too many checks; slow down")];
    let body;
    try { body = await res.json(); } catch { body = null; }
    if (!res.ok || !body || typeof body !== "object") {
      return [502, failure(service, "upstream_error", `HISTOR answered ${res.status}`)];
    }
    return [200, ok(service, { source: historUrl, check: body })];
  };
  return service;
}

// ── warden-scan ─────────────────────────────────────────────────────────────────────────
// The caller sends a server's tools/list; WARDEN's static rule table and its built-in threat
// deny-list decide whether a host should expose those definitions to a model. Pure function of
// the input: no network, no state. Origin and pinning are host state and are not run here.

const POLICY = Object.freeze({
  blockAtSeverity: "high",
  sensitiveToolPatterns: [],
  allowUnknownServers: true,
  pinToolDefs: false,
});

function cleanTool(t) {
  if (!t || typeof t !== "object" || typeof t.name !== "string" || !t.name.trim()) return null;
  const text = (v) => (typeof v === "string" ? v.slice(0, MAX_TEXT) : undefined);
  const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : undefined);
  const tool = { name: t.name.slice(0, 200), description: text(t.description) ?? "", inputSchema: obj(t.inputSchema) ?? {} };
  for (const [k, v] of [["title", text(t.title)], ["outputSchema", obj(t.outputSchema)], ["annotations", obj(t.annotations)]]) {
    if (v !== undefined) tool[k] = v;
  }
  return tool;
}

function wardenScan() {
  const warden = new Warden({ gates: [new StaticScanGate(), new ThreatGate(new ThreatFeed({}))], policy: POLICY });
  const service = {
    id: "warden-scan",
    methods: ["POST"],
    fields: [
      { name: "tools", type: "array", required: true,
        description: `the server's tools/list result: [{name, description, inputSchema, ...}], at most ${MAX_TOOLS}` },
      { name: "server", type: "object", required: false,
        description: "optional {name, url} of the server, used only to label the verdict" },
    ],
  };
  service.handle = async (params) => {
    const raw = Array.isArray(params.tools) ? params.tools : Array.isArray(params.tools?.tools) ? params.tools.tools : null;
    if (!raw || raw.length === 0) return [200, inputRequired(service, "send tools: the server's tools/list result")];
    if (raw.length > MAX_TOOLS) return [400, failure(service, "too_many_tools", `at most ${MAX_TOOLS} tools per scan`)];
    const tools = raw.map(cleanTool);
    const bad = tools.findIndex((t) => t === null);
    if (bad >= 0) return [400, failure(service, "bad_tool", `tools[${bad}] needs a non-empty string name`)];
    const s = params.server && typeof params.server === "object" ? params.server : {};
    const label = typeof s.name === "string" && s.name.trim() ? s.name.trim().slice(0, 200) : "submitted";
    const server = { id: label, name: label, transport: "http",
                     ...(typeof s.url === "string" ? { url: s.url.slice(0, 2048) } : {}) };
    const v = await warden.vet(server, tools);
    return [200, ok(service, {
      engine: { package: `@aimarket/warden@${WARDEN_VERSION}`, ruleset: v.rulesets.staticScan },
      verdict: {
        allow: v.allow,
        score: v.score,
        decidedBy: v.decidedBy ?? null,
        blockedTools: v.blockedTools,
        allowedTools: v.allowedTools,
        findings: v.findings.map((f) => ({
          gate: f.gate, code: f.code, severity: f.severity, tool: f.tool ?? null,
          advisory: Boolean(f.advisory), message: f.message,
        })),
      },
      scope: "tool definitions only: static rules + built-in threat list; origin and pinning are host state and not checked",
    })];
  };
  return service;
}

export function buildServices(opts) {
  const list = [historCheck(opts), wardenScan()];
  return new Map(list.map((s) => [s.id, s]));
}

export function callerIdFor(ip) {
  return createHash("sha256").update(`okx-a2mcp|${ip}`).digest("hex").slice(0, 32);
}

export { STATIC_SCAN_RULESET_VERSION, WARDEN_VERSION };
