// Paid twins of the free A2MCP services, for agents that pay over x402: USDC on Base, verified and
// settled by the CDP facilitator, described for the CDP Bazaar so wallets can discover them.
//
// The facilitator authenticates with a CDP secret API key. It is read from a JSON file
// ({id, privateKey}, as the CDP portal downloads it) and passed to the SDK in memory, so it never
// appears in the container's environment or in `docker inspect`.
import { readFileSync } from "node:fs";
import { HUB_TOOLS } from "./hub.js";

const BASE_MAINNET = "eip155:8453";

/** Bazaar metadata per service: what an agent sees before it pays. */
const LISTING = {
  "histor-check": {
    description:
      "HISTOR pre-flight for an MCP server: its signed record in the HISTOR transparency log — when the tool set was first seen, whether it changed, what the pattern scan found. Never contacts the server asked about.",
    tags: ["mcp", "security", "transparency-log", "trust"],
    icon: "https://modelmarket.dev/.well-known/erc-8004/histor.png",
    input: { endpoint: "https://mcp.redu.cloud/mcp" },
    inputSchema: {
      type: "object",
      properties: {
        endpoint: { type: "string", description: "https URL of the MCP server (send this or name)" },
        name: { type: "string", description: "registry name, e.g. io.github.owner/server (send this or endpoint)" },
      },
    },
    output: { status: "ok", service: "histor-check", check: { type: "histor.check/v1", match: "no-digest", target: { name: "cloud.redu/mcp" } } },
  },
  "warden-scan": {
    description:
      "WARDEN verdict on an MCP server's tools/list: allow or block, a 0-1 score and every finding with the matched text (prompt injection, secret requests, exfiltration, hidden Unicode). Deterministic published rules, no network.",
    tags: ["mcp", "security", "prompt-injection", "firewall"],
    icon: "https://modelmarket.dev/.well-known/erc-8004/warden.png",
    input: { tools: [{ name: "get_weather", description: "Returns the forecast for a city.", inputSchema: { type: "object" } }] },
    inputSchema: {
      type: "object",
      properties: {
        tools: {
          type: "array",
          description: "the server's tools/list result, up to 500 definitions",
          items: { type: "object", properties: { name: { type: "string" }, description: { type: "string" }, inputSchema: { type: "object" } }, required: ["name"] },
        },
        server: { type: "object", description: "optional {name, url}, used only as a label" },
      },
      required: ["tools"],
    },
    output: { status: "ok", service: "warden-scan", verdict: { allow: true, score: 1, findings: [] } },
  },
  // The hub's direct capabilities, each at the hub's own price (src/hub.js).
  ...Object.fromEntries(Object.entries(HUB_TOOLS).map(([id, t]) => [id, {
    description: t.description,
    tags: t.tags,
    icon: "https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.png",
    price: t.price,
    input: t.example,
    inputSchema: {
      type: "object",
      properties: Object.fromEntries(t.fields.map((f) => [f.name, { type: f.type, description: f.description }])),
      ...(t.fields.some((f) => f.required) ? { required: t.fields.filter((f) => f.required).map((f) => f.name) } : {}),
    },
    output: { status: "ok", service: id, capability_id: t.capability_id, result: {}, receipt: {} },
  }])),
};

/**
 * OpenAPI 3.1 for the paid routes, built from the same listing the Bazaar reads, so the two
 * cannot drift. Circle's Agent Marketplace asks for one; any agent can read it too.
 */
export function openapiDocument({ publicUrl, payTo, serviceIds, network = BASE_MAINNET }) {
  const paths = {};
  for (const id of serviceIds) {
    const l = LISTING[id];
    if (!l) continue;
    paths[`/x402/${id}`] = {
      post: {
        operationId: id.replace(/-([a-z])/g, (_, c) => c.toUpperCase()),
        summary: l.description.split(". ")[0].replace(/\.$/, ""),
        description: l.description,
        tags: l.tags,
        // The agentcash/x402scan discovery profile: structured price + protocols; the rest is detail.
        "x-payment-info": {
          price: { mode: "fixed", currency: "USD", amount: (l.price ?? "$0.001").replace(/^\$/, "") },
          protocols: [{ x402: { scheme: "exact", network, asset: "USDC", payTo } }],
        },
        security: [],
        requestBody: { required: true, content: { "application/json": { schema: l.inputSchema, example: l.input } } },
        responses: {
          200: { description: "The result (paid).", content: { "application/json": { example: l.output } } },
          400: { description: "Missing or invalid input. Not settled: the buyer pays nothing." },
          402: { description: "Payment required: the x402 V2 terms are in the PAYMENT-REQUIRED header.",
                 headers: { "PAYMENT-REQUIRED": { schema: { type: "string" }, description: "base64 JSON x402 payment terms" } } },
          429: { description: "Per-caller rate limit." },
          502: { description: "The upstream service failed. Not settled." },
        },
      },
    };
  }
  return {
    openapi: "3.1.0",
    info: {
      title: "AIMarket x402 services",
      version: "1.0.0",
      description: "Signed real-world data, verifiable randomness and MCP security checks, paid per call over x402 (USDC on Base). Every paid response carries a signed receipt where the service issues one.",
      contact: { url: "https://modelmarket.dev" },
    },
    servers: [{ url: publicUrl || "https://modelmarket.dev" }],
    paths,
  };
}

/** The /.well-known/x402 manifest: this host is a resource server; its paid routes, all same-origin. */
export function wellKnownManifest({ publicUrl, serviceIds }) {
  const base = (publicUrl || "https://modelmarket.dev").replace(/\/$/, "");
  return {
    x402Version: 2,
    kind: "resource-server",
    name: "AIMarket",
    description: "Signed real-world data, verifiable randomness and MCP security checks, paid per call over x402 (USDC on Base).",
    resources: serviceIds.filter((id) => LISTING[id]).map((id) => ({
      url: `${base}/x402/${id}`, method: "POST", description: LISTING[id].description.split(". ")[0].replace(/\.$/, ""),
    })),
    attestation: { type: "none" },
    docs: `${base}/x402/openapi.json`,
  };
}

/** What one paid route costs: its own listed price, else the gateway default. */
export function priceOf(id, fallback = "$0.001") {
  return LISTING[id]?.price ?? fallback;
}

/**
 * Build the payment middleware for POST /x402/<service>, or return null when x402 is not
 * configured (no key file or no receiving address) — the free routes are unaffected either way.
 */
export async function buildPaywall({ keyFile, payTo, price = "$0.001", publicUrl, serviceIds }) {
  if (!keyFile || !payTo) return null;
  const key = JSON.parse(readFileSync(keyFile, "utf8"));
  const [{ createX402Server }, { paymentMiddlewareFromHTTPServer }, { declareDiscoveryExtension }] = await Promise.all([
    import("@coinbase/cdp-sdk/x402"),
    import("@x402/express"),
    import("@x402/extensions/bazaar"),
  ]);
  const routes = {};
  for (const id of serviceIds) {
    const l = LISTING[id];
    if (!l) continue;
    routes[`POST /x402/${id}`] = {
      accepts: { scheme: "exact", price: l.price ?? price, network: BASE_MAINNET, payTo },
      resource: `${publicUrl}/x402/${id}`,
      description: l.description,
      mimeType: "application/json",
      serviceName: "AIMarket",
      tags: l.tags,
      iconUrl: l.icon,
      extensions: {
        ...declareDiscoveryExtension({
          method: "POST",
          bodyType: "json",
          input: l.input,
          inputSchema: l.inputSchema,
          output: { example: l.output },
        }),
      },
    };
  }
  const server = await createX402Server({
    apiKeyId: key.id,
    apiKeySecret: key.privateKey,
    environment: "production",
    payToConfig: { type: "address", evm: payTo },
    routes,
  });
  return {
    middleware: paymentMiddlewareFromHTTPServer(server),
    payTo: server.payToEvmAddress ?? payTo,
    price,
    network: BASE_MAINNET,
    paths: Object.keys(routes),
  };
}

/**
 * A paywall that never takes the gateway down with it. The CDP facilitator is fetched while the
 * paywall is built; when that fails (an outage, a revoked key) the free /a2mcp routes must still
 * serve, so the build is retried in the background and the paid routes answer 503 until it lands.
 * Returns null when x402 is not configured at all.
 */
export function resilientPaywall(config, { log = console, retryMs = [5_000, 15_000, 60_000, 300_000], build = buildPaywall } = {}) {
  if (!config.keyFile || !config.payTo) return null;
  const price = config.price ?? "$0.001";
  const paths = config.serviceIds.filter((id) => LISTING[id]).map((id) => `POST /x402/${id}`);
  let current = null;
  const state = { ready: false, lastError: null };
  const attempt = async (n = 0) => {
    try {
      current = await build(config);
      state.ready = true; state.lastError = null;
      log.log?.(`x402 ready: ${current.price} on ${current.network} to ${current.payTo}`);
    } catch (e) {
      state.lastError = e instanceof Error ? e.message : String(e);
      const wait = retryMs[Math.min(n, retryMs.length - 1)];
      log.error?.(`x402 unavailable (${state.lastError}); free routes unaffected; retrying in ${wait / 1000}s`);
      setTimeout(() => attempt(n + 1), wait).unref?.();
    }
  };
  const ready = attempt();
  return {
    price, network: BASE_MAINNET, payTo: config.payTo, paths, state, ready,
    middleware(req, res, next) {
      if (current) return current.middleware(req, res, next);
      if (req.method === "POST" && paths.includes(`POST ${req.path}`)) {
        res.set("Retry-After", "60");
        return res.status(503).json({ status: "error", error: "x402_unavailable", message: "the payment facilitator is unreachable; try again shortly" });
      }
      return next();
    },
  };
}
