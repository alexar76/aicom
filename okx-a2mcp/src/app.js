import { randomBytes } from "node:crypto";
import express from "express";
import { failure, paramsOf } from "./a2mcp.js";
import { buildServices, callerIdFor, WARDEN_VERSION } from "./services.js";
import { hubServices } from "./hub.js";
import { openapiDocument, priceOf, wellKnownManifest } from "./x402.js";

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

export function createApp({
  historUrl = "https://histor.modelmarket.dev",
  fetchImpl = globalThis.fetch,
  timeoutMs = 10_000,
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
} = {}) {
  const services = buildServices({ historUrl: historUrl.replace(/\/+$/, ""), fetchImpl, timeoutMs, freePerMinute: freeHistorPerMinute, now });
  // Paid-only twins of the hub's capabilities, when the gateway has a hub account (src/hub.js).
  for (const s of hubServices({ hubUrl, apiKey: hubApiKey, fetchImpl })) services.set(s.id, s);
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

  if (paywall) {
    // Machine-readable description of the paid routes. The hub folds it into the origin's
    // /openapi.json (AIMARKET_OPENAPI_MERGE_URLS), which is where x402 indexers read it.
    const paidIds = () => paywall.paths.map((p) => p.replace("POST /x402/", ""));
    app.get("/x402/openapi.json", (_req, res) => {
      res.json(openapiDocument({ publicUrl, payTo: paywall.payTo, serviceIds: paidIds() }));
    });
    // The x402 capability manifest (draft-hawkins-x402-dns-discovery), served at
    // /.well-known/x402 by the origin's nginx.
    app.get(["/.well-known/x402", "/x402/well-known.json"], (_req, res) => {
      res.set("Cache-Control", "public, max-age=3600").json(wellKnownManifest({ publicUrl, serviceIds: paidIds() }));
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
    app.use(paywall.middleware);
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
