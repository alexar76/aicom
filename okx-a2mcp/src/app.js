import express from "express";
import { failure, paramsOf } from "./a2mcp.js";
import { buildServices, callerIdFor, WARDEN_VERSION } from "./services.js";

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
  now = () => Date.now(),
} = {}) {
  const services = buildServices({ historUrl: historUrl.replace(/\/+$/, ""), fetchImpl, timeoutMs });
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
        price: "free",
        fields: s.fields,
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
      const [status, body] = await service.handle(paramsOf(req), { callerId: callerIdFor(ip) });
      return res.status(status).json(body);
    } catch {
      return res.status(500).json(failure(service, "internal_error", "the service failed; try again"));
    }
  });

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
