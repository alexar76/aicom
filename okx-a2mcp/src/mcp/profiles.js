// Free MCP servers by topic at /tools/mcp/<profile>, for MCP directories (Smithery and the like)
// where people look for one kind of tool: weather, business facts, MCP security. Owner 2026-10-20:
// free with limits. A directory's gateway calls on behalf of all its users from a few addresses,
// so a per-caller trial would run out on the first calls; the limits here are shared per profile,
// per minute and per day, and the daily one bounds what the gateway's hub credit can spend.
//
// Three kinds of tools:
//   hub      — bought from the hub with the gateway's credit account (weather, SYMMARTYS);
//   service  — this gateway's own free services (WARDEN scan, HISTOR lookup, tool-list cost);
//   hearth   — a HESTIA agent on the hearth's shared free budget (x402 check).
// mcp.tools.diff stays off MCP: its answer quotes injected text back into the caller's model.
import { readFileSync } from "node:fs";
import { HUB_TOOLS } from "../hub.js";

const SYMMARTYS = JSON.parse(readFileSync(new URL("./symmartys-tools.json", import.meta.url), "utf8"));

// The provider's manifest has no titles, and a directory reviewer reads them, so they are named here.
const SYMMARTYS_TITLES = {
  vat_check: "VAT number check (VIES)",
  sanctions_screen: "Sanctions list screening",
  company_lookup: "Company register lookup",
  lei_lookup: "LEI lookup (GLEIF)",
  fx_rate: "ECB reference exchange rate",
  business_days: "Business days and holidays",
  eori_check: "EORI number check",
  domain_rdap: "Domain registration data (RDAP)",
};
// The manifest is written for paid calls: "A registry that is down costs nothing." means the call is
// not charged. These tools are free, so the sentence only confuses here.
const unpaid = (description) => description.replace(/\s*A [^.]*\bcosts nothing\.\s*$/, "");

const LAT = { type: "number", minimum: -90, maximum: 90, description: "Latitude in degrees" };
const LON = { type: "number", minimum: -180, maximum: 180, description: "Longitude in degrees" };
const CITY = { type: "string", maxLength: 120, description: "A city instead of coordinates, e.g. Tokyo" };

const hubTool = (name, id, inputSchema, title) => {
  const t = HUB_TOOLS[id];
  return { name, title, kind: "hub", call: { product_id: t.product_id, capability_id: t.capability_id, source_hub: t.source_hub },
           build: t.build, need: t.need, description: t.description, inputSchema, x402: `/x402/${id}` };
};

export const PROFILES = {
  weather: {
    title: "Live weather and air quality (GAIA)",
    description: "Current weather, air quality and the nearest live public sensors for any place on Earth, each answer with a signed receipt. Free, no key.",
    perMinute: 30, perDay: 500,
    tools: [
      hubTool("weather_now", "weather-now", { type: "object", properties: { latitude: LAT, longitude: LON, city: CITY } }, "Current weather"),
      hubTool("air_quality_now", "air-quality-now", { type: "object", properties: { latitude: LAT, longitude: LON, city: CITY } }, "Current air quality"),
      hubTool("nearby_sensors", "nearby-sensors", {
        type: "object", required: ["latitude", "longitude"],
        properties: {
          latitude: LAT, longitude: LON,
          layers: { type: "array", items: { type: "string" }, description: "Sensor layers, e.g. [\"weather\", \"air\", \"radiation\", \"quake\"]; default weather" },
          max_km: { type: "number", minimum: 0, description: "Refuse sensors farther than this" },
        },
      }, "Nearest live sensors"),
    ],
  },
  symmartys: {
    title: "Business facts from public registers (SYMMARTYS)",
    description: "EU VAT and EORI validity, sanctions screening (OFAC, EU, UK, UN), company and LEI lookup, ECB exchange rates, business days and domain registration data — answered from the official public sources, each with a signed receipt. Free, no key.",
    perMinute: 30, perDay: 300,
    tools: SYMMARTYS.tools.map((t) => ({
      name: t.name, title: SYMMARTYS_TITLES[t.name] ?? t.name.replace(/_/g, " "), kind: "hub",
      call: { product_id: t.product_id, capability_id: t.capability_id, source_hub: SYMMARTYS.source_hub },
      build: (p) => (p && typeof p === "object" && !Array.isArray(p) ? p : null),
      need: "send the input the schema describes",
      description: unpaid(t.description), inputSchema: t.input_schema,
    })),
  },
  domains: {
    title: "Domain availability and price quotes (Domain Operator Kit demo)",
    description: "Is a .com, .net or .org name free, and what would one year cost? Availability comes from the registries' own RDAP; the quote is signed by the seller. This is the demo seller of the open-source Domain Operator Kit: prices are illustrative and orders are refused, so nothing is bought. Free, no key.",
    perMinute: 30, perDay: 1000,
    tools: [
      { name: "domain_quote", title: "Domain availability and quote", kind: "hub",
        call: { product_id: "domains-modelmarket", capability_id: "domains.quote@v1", source_hub: "https://domains.modelmarket.dev" },
        build: (p) => (typeof p.domain === "string" && p.domain.trim() && p.domain.length <= 253 ? { domain: p.domain.trim().toLowerCase() } : null),
        need: "send domain, an exact .com, .net or .org name such as example.com",
        description: "Check whether an exact .com, .net or .org domain is available and get a signed one-year quote: supplier cost, the seller's fixed markup and the total in USDC. Availability is read from the registry's RDAP and is not a reservation. Demo seller: prices are illustrative and register/renew are refused with demo_mode.",
        inputSchema: { type: "object", required: ["domain"], properties: {
          domain: { type: "string", maxLength: 253, description: "An exact registrable domain, e.g. example.com", examples: ["example.com"] } } } },
    ],
  },
  security: {
    title: "MCP security checks (WARDEN, HISTOR)",
    description: "Scan an MCP server's tool definitions for prompt injection, exfiltration and credential theft with WARDEN, look up a server's tool-set history in the HISTOR transparency log, count what its tool list costs in tokens per request, and check an x402 payment signature. Free, no key.",
    perMinute: 60, perDay: 3000,
    tools: [
      { name: "warden_scan", title: "Scan tool definitions (WARDEN)", kind: "service", service: "warden-scan",
        description: "Scan an MCP server's tools/list with WARDEN, the open-source MCP firewall: static rules and a threat list over every name, description, schema and annotation. Returns allow or block and each finding with its rule and severity. Quoted fragments of the scanned text are left out of the answer.",
        inputSchema: { type: "object", required: ["tools"], properties: {
          tools: { type: "array", items: { type: "object" }, description: "The server's tools/list result: [{name, description, inputSchema, ...}]" },
          server: { type: "object", description: "Optional {name, url} to label the verdict" } } } },
      { name: "histor_check", title: "Server history (HISTOR)", kind: "service", service: "histor-check",
        description: "Look up an MCP server in HISTOR, a public append-only log of MCP tool sets: when its tool set was first pinned, how often it changed, and what the pattern scan found. HISTOR answers from its own observations and never contacts the server.",
        inputSchema: { type: "object", properties: {
          endpoint: { type: "string", description: "https URL of the MCP server" },
          name: { type: "string", description: "Or its registry name, e.g. io.github.owner/server" } } } },
      { name: "tool_list_cost", title: "Tool list token cost", kind: "service", service: "tool-list-cost",
        description: "How many tokens an MCP server's tool list adds to every model request, what that costs per 1,000 requests, the heaviest tools, and where it sits among 18,204 packages and 16,170 remote servers. Send a tools/list or name a server HISTOR observes.",
        inputSchema: { type: "object", properties: {
          tools: { type: "array", items: { type: "object" }, description: "A tools/list result" },
          server: { type: "string", description: "Or a server HISTOR observes: https endpoint, npm:<package>, pypi:<package> or registry name" } } } },
      { name: "x402_check", title: "x402 payment check", kind: "service", service: "x402-check", web: true,
        description: "Check a signed x402 USDC payment before submitting it: recovers the EIP-712 signer, runs USDC's own checks and the seller's terms, and when the signature fails names the domain it was really made for (e.g. Base Sepolia's 'USDC' used on Base, where USDC is 'USD Coin').",
        inputSchema: { type: "object", properties: {
          x_payment: { type: "string", description: "The X-PAYMENT header (base64)" },
          requirements: { type: "object", description: "The 402's accepts entry: payTo, amount, asset, network" },
          authorization: { type: "object", description: "Instead of x_payment: from, to, value, validAfter, validBefore, nonce" },
          signature: { type: "string", description: "With authorization: the 65-byte hex signature" },
          network: { type: "string", description: "With authorization: base, base-sepolia, … or eip155:<id>" } } } },
    ],
  },
};
