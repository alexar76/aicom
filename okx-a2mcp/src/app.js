import { createHash, randomBytes } from "node:crypto";
import express from "express";
import { failure, paramsOf } from "./a2mcp.js";
import { buildServices, callerIdFor, WARDEN_VERSION } from "./services.js";
import { hearthServices } from "./hearth.js";
import { hubServices } from "./hub.js";
import { openapiDocument, priceOf, wellKnownManifest } from "./x402.js";
import { mountTools } from "./web/routes.js";
import { mountMcp } from "./mcp/server.js";

/** The paying wallet named inside an x402 payment header (base64 JSON), lower-cased, or "". */
export function payerOf(header) {
  try {
    const doc = JSON.parse(Buffer.from(String(header), "base64").toString("utf8"));
    const from = doc?.payload?.authorization?.from ?? doc?.payload?.from ?? "";
    return /^0x[0-9a-fA-F]{40}$/.test(from) ? from.toLowerCase() : "";
  } catch {
    return "";
  }
}

/** Fixed-window counter per caller and service; in memory, because one process serves it. */
function rateLimiter(perMinute, now) {
  const windows = new Map();
  return (key) => {
    const minute = Math.floor(now() / 60_000);
    const w = windows.get(key);
    if (!w || w.minute !== minute) {
      if (windows.size > 50_000) windows.clear();  // bounded: a flood of addresses cannot grow it forever
      windows.set(key, { minute, n: 1 });
      return true;
    }
    w.n += 1;
    return w.n <= perMinute;
  };
}

/**
 * The paywall with its challenge in the 402 body as well as the PAYMENT-REQUIRED header.
 * x402 V2 answers with an empty body and the challenge in the header only; probes that read the
 * body saw no x402Version and no accepts — Karatum rated HISTOR and WARDEN "did not answer as
 * x402" for a 402 that carried a valid challenge (2026-10-23). Only an empty 402 body is filled,
 * and only from the header the paywall itself set.
 */
function challengeInBody(middleware) {
  return (req, res, next) => {
    const json = res.json.bind(res);
    res.json = (body) => {
      res.json = json;
      const header = res.statusCode === 402 ? res.getHeader("payment-required") : null;
      if (header && body && typeof body === "object" && !Array.isArray(body) && !Object.keys(body).length) {
        try { body = JSON.parse(Buffer.from(String(header), "base64").toString("utf8")); } catch { /* keep {} */ }
      }
      return json(body);
    };
    return middleware(req, res, next);
  };
}

export function createApp({
  historUrl = "https://histor.modelmarket.dev",
  fetchImpl = globalThis.fetch,
  timeoutMs = 12_000, // per attempt; histor-check tries twice (src/services.js)
  perMinute = 30,
  publicUrl = "",
  // nginx reaches a published container through docker-proxy, so the peer is the bridge gateway
  // (172.16/12), not loopback. Trusting only loopback put every caller in one rate-limit bucket.
  trustProxy = "loopback, uniquelocal",
  // Optional x402 paywall from src/x402.js: adds paid twins at POST /x402/<service>.
  paywall = null,
  // Key for the buyer id sent to HISTOR (CALLER_ID_SECRET). Without one, a random key per process:
  // ids stay stable for its lifetime and mean nothing outside it.
  callerSecret = randomBytes(32),
  // Free histor-check calls across all callers, kept under HISTOR's 300/min ceiling for us.
  freeHistorPerMinute = 200,
  now = () => Date.now(),
  // The hub the paid capability twins buy from, and the gateway's credit-account key there.
  hubUrl = "https://modelmarket.dev",
  hubApiKey = "",
  // The hearth two HESTIA agents are bought from (src/hearth.js), and this gateway's seller key there.
  hearthUrl = "https://hestia.modelmarket.dev",
  hearthApiKey = "",
  // The free pages for people at /tools/ (src/web): checks per minute per address and tool, and
  // the HESTIA agents' shared free budget across everyone (they run in the hearth's sandbox).
  webPerMinute = 10,
  freeHearthPerMinute = 60,
  // Google Search Console's HTML-tag token for the https://modelmarket.dev/tools/ property (public).
  siteVerification = "",
  // Our own addresses (AICOM_OWN_IPS on the host): left out of the MCP request counters.
  ownIps = new Set(),
  // Start the tool-list counter's worker at boot and keep it (src/toolcost.js); the server does.
  warmToolCounter = false,
} = {}) {
  const services = buildServices({ historUrl: historUrl.replace(/\/+$/, ""), fetchImpl, timeoutMs, freePerMinute: freeHistorPerMinute, now,
                                   warmCounter: warmToolCounter });
  // Paid-only twins of the hub's capabilities, when the gateway has a hub account (src/hub.js).
  for (const s of hubServices({ hubUrl, apiKey: hubApiKey, fetchImpl })) services.set(s.id, s);
  for (const s of hearthServices({ hearthUrl, apiKey: hearthApiKey, sellerUrl: publicUrl, fetchImpl,
                                   freePerMinute: freeHearthPerMinute, now })) services.set(s.id, s);
  const allow = rateLimiter(perMinute, now);
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", trustProxy);  // behind the host's nginx: the caller is X-Forwarded-For
  // Any content type: agents send JSON without always saying so. An empty body is skipped.
  app.use(express.json({ limit: "1mb", type: () => true }));

  app.get("/health", (_req, res) => res.json({ ok: true, services: [...services.keys()], warden: WARDEN_VERSION }));

  // Machine-readable list of what this endpoint sells, with each service's parameters.
  app.get("/a2mcp", (_req, res) => {
    res.json({
      provider: "AIMarket (modelmarket.dev)",
      services: [...services.values()].map((s) => ({
        id: s.id,
        endpoint: `${publicUrl}/a2mcp/${s.id}`,
        methods: s.methods,
        price: s.paidOnly ? `x402 only, ${priceOf(s.id)}` : "free",
        fields: s.fields,
        ...(paywall && paywall.paths.includes(`POST /x402/${s.id}`)
          ? { x402: { endpoint: `${publicUrl}/x402/${s.id}`, method: "POST", price: priceOf(s.id, paywall.price),
                      network: paywall.network, asset: "USDC", payTo: paywall.payTo } }
          : {}),
      })),
    });
  });

  app.all("/a2mcp/:service", async (req, res) => {
    const service = services.get(req.params.service);
    if (!service) return res.status(404).json({ status: "error", error: "unknown_service", services: [...services.keys()] });
    if (!service.methods.includes(req.method)) {
      return res.status(405).set("Allow", service.methods.join(", "))
        .json(failure(service, "method_not_allowed", `use ${service.methods.join(" or ")}`));
    }
    const ip = req.ip || "unknown";
    if (!allow(`${service.id}|${ip}`)) {
      return res.status(429).set("Retry-After", "60").json(failure(service, "rate_limited", `at most ${perMinute} calls a minute`));
    }
    try {
      const [status, body] = await service.handle(paramsOf(req), { callerId: callerIdFor(ip, callerSecret) });
      return res.status(status).json(body);
    } catch {
      return res.status(500).json(failure(service, "internal_error", "the service failed; try again"));
    }
  });

  // Free MCP servers by topic (src/mcp): before the pages, whose router answers 404 for the rest of /tools/.
  mountMcp(app, {
    services,
    hub: { base: hubUrl.replace(/\/+$/, ""), apiKey: hubApiKey, fetchImpl, timeoutMs: 30_000 },
    origin: publicUrl || "https://modelmarket.dev",
    callerIdOf: (ip) => callerIdFor(ip, callerSecret),
    ownIps,
    now,
  });

  // The people's pages and their API. Before the paywall: nothing under /tools/ is ever paid.
  mountTools(app, {
    services,
    allow: rateLimiter(webPerMinute, now),
    callerIdOf: (ip) => callerIdFor(ip, callerSecret),
    origin: publicUrl || "https://modelmarket.dev",
    verification: siteVerification,
  });

  if (paywall) {
    // Machine-readable description of the paid routes. The hub folds it into the origin's
    // /openapi.json (AIMARKET_OPENAPI_MERGE_URLS), which is where x402 indexers read it.
    const paidIds = () => paywall.paths.map((p) => p.replace("POST /x402/", ""));
    const guard = challengeInBody((req, res, next) => paywall.middleware(req, res, next));
    app.get("/x402/openapi.json", (_req, res) => {
      res.json(openapiDocument({ publicUrl, payTo: paywall.payTo, serviceIds: paidIds() }));
    });
    // The x402 capability manifest (draft-hawkins-x402-dns-discovery), served at
    // /.well-known/x402 by the origin's nginx.
    app.get(["/.well-known/x402", "/x402/well-known.json"], (_req, res) => {
      res.set("Cache-Control", "public, max-age=3600").json(wellKnownManifest({ publicUrl, serviceIds: paidIds() }));
    });
    // A paid route is POST-only, but an unpaid GET gets the same 402 a POST gets. Probes send a
    // GET: our 404 there read as down every day — agenteconomy.report rated us D at 0 % uptime,
    // Karatum "unreachable" (2026-10-21). A 405 satisfied agenteconomy, which then POSTs, but
    // Karatum takes only a 402 to the GET. A GET carrying a payment is never verified or
    // settled: it gets the 405. Unknown names still get the 404.
    app.all("/x402/:service", (req, res, next) => {
      if (req.method !== "GET" && req.method !== "HEAD") return next();
      if (!paidIds().includes(req.params.service)) return next();
      const service = services.get(req.params.service) || { id: req.params.service };
      const refuse = () => res.status(405).set("Allow", "POST")
        .json(failure(service, "method_not_allowed", "use POST with a JSON body; it answers 402 with the price until paid"));
      if (req.get("payment-signature") || req.get("x-payment")) return refuse();
      res.set("Allow", "POST");
      // The paywall matches "POST /x402/<id>": shown as a POST, the unpaid GET gets its challenge
      // (or its 503 while the facilitator is down). Without a payment it never calls next().
      const method = req.method;
      req.method = "POST";
      return guard(req, res, () => { req.method = method; refuse(); });
    });
    // The middleware answers 402 for the configured routes until a valid payment arrives, and
    // settles only when the handler answers below 400 — so a refused request costs nothing.
    // The per-caller limit runs BEFORE the paywall: the middleware asks the CDP facilitator to
    // verify every payment it is shown, under our API key, so a limit after it would let anyone
    // spend our facilitator quota with copied payment headers.
    app.post("/x402/:service", (req, res, next) => {
      const service = services.get(req.params.service);
      if (!service) return next();
      if (!allow(`x402|${service.id}|${req.ip || "unknown"}`)) {
        return res.status(429).set("Retry-After", "60").json(failure(service, "rate_limited", `at most ${perMinute} calls a minute`));
      }
      return next();
    });
    // One payment, one call in flight. The paywall verifies on entry and settles only after the
    // handler answers, and the handler spends upstream (hub credit, seller keys) before that:
    // N concurrent requests carrying the same payment header — or N authorizations from a
    // wallet that can cover one — all passed verify, all ran, and at most one settled.
    const inFlight = new Set();
    app.post("/x402/:service", (req, res, next) => {
      const header = String(req.get("payment-signature") || req.get("x-payment") || "");
      if (!header) return next();
      const keys = [`h:${createHash("sha256").update(header).digest("hex")}`];
      const payer = payerOf(header);
      if (payer) keys.push(`p:${payer}`);
      if (keys.some((k) => inFlight.has(k))) {
        const service = services.get(req.params.service);
        return res.status(409).set("Retry-After", "5").json(
          failure(service || { id: req.params.service }, "payment_in_flight",
                  "a call paid by this payment or wallet is still running; retry when it answers"));
      }
      keys.forEach((k) => inFlight.add(k));
      let released = false;
      const release = () => { if (!released) { released = true; keys.forEach((k) => inFlight.delete(k)); } };
      res.on("finish", release);
      res.on("close", release);
      return next();
    });
    app.use(guard);
    app.post("/x402/:service", async (req, res) => {
      const service = services.get(req.params.service);
      if (!service) return res.status(404).json({ status: "error", error: "unknown_service", services: [...services.keys()] });
      const ip = req.ip || "unknown";
      try {
        const [status, body] = await service.handle(paramsOf(req), { callerId: callerIdFor(ip, callerSecret), paid: true });
        // A paid call with missing parameters is refused, not answered: 200 would be settled.
        return res.status(body?.status === "input_required" ? 400 : status).json(body);
      } catch {
        return res.status(500).json(failure(service, "internal_error", "the service failed; try again"));
      }
    });
  }

  app.use((req, res) => res.status(404).json({ status: "error", error: "not_found", see: "/a2mcp" }));
  // Malformed JSON or an oversized body arrives here from express.json().
  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    const status = err?.status === 413 ? 413 : 400;
    res.status(status).json({ status: "error", error: status === 413 ? "body_too_large" : "bad_json",
                              message: status === 413 ? "body is limited to 1 MB" : "body must be JSON" });
  });
  return app;
}
