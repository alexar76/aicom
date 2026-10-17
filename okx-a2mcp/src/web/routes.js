// /tools/: the free pages for people and the one API they call. The API answers exactly what
// the agent routes answer (same services, same handlers), so the page can say "this is what an
// agent pays for" and mean it. Its own limits: a per-address budget per tool, and for the two
// HESTIA agents the shared free budget in src/hearth.js.
import express from "express";
import { failure } from "../a2mcp.js";
import { readFileSync } from "node:fs";
import { LANGS } from "./i18n/index.js";
import { ASSETS, TOOL_IDS, renderIndex, renderNotFound, renderTool, robots, sitemap } from "./pages.js";

// Scripts only from this origin; styles and fonts only from this origin (the hub serves
// /assets/*); the form talks to this origin only. Nothing may frame the page.
/** Public by design (scripts/indexnow.mjs); kept in a file so the script and the route share it. */
export const INDEXNOW_KEY = readFileSync(new URL("./indexnow-key.txt", import.meta.url), "utf8").trim();

const CSP = [
  "default-src 'none'", "script-src 'self'", "style-src 'self'", "font-src 'self'", "img-src 'self' data:",
  "connect-src 'self'", "base-uri 'none'", "form-action 'self'", "frame-ancestors 'none'",
].join("; ");

function html(res, status, body) {
  res.status(status).set({
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": status === 200 ? "public, max-age=300" : "no-store",
  }).send(body);
}

export function mountTools(app, { services, allow, callerIdOf, origin, verification = "" }) {
  const opts = { origin, verification };
  const isLang = (l) => LANGS.includes(l) && l !== "en";
  const isTool = (id) => TOOL_IDS.includes(id) && services.has(id);

  // Strict: "/tools/ru" and "/tools/ru/" are different pages (one redirects to the other); the
  // app's default routing treats them as one and the redirect would loop.
  const r = express.Router({ strict: true });
  // IndexNow proves the site by its key file; under /tools/ it vouches for the /tools/ pages only.
  r.get(`/${INDEXNOW_KEY}.txt`, (_req, res) => res.type("text/plain").send(INDEXNOW_KEY));
  r.get("/robots.txt", (_req, res) =>
    res.type("text/plain").set("Cache-Control", "public, max-age=3600").send(robots(origin)));
  r.get("/sitemap.xml", (_req, res) =>
    res.type("application/xml").set("Cache-Control", "public, max-age=3600").send(sitemap(origin)));
  r.get("/assets/:file", (req, res) => {
    const a = ASSETS[req.params.file];
    if (!a) return res.status(404).type("text/plain").send("not found");
    // The pages link each asset with ?v=<its hash>, so a versioned request can be kept for good.
    const immutable = req.query.v === a.version;
    return res.set({
      "Content-Type": a.type,
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": immutable ? "public, max-age=31536000, immutable" : "public, max-age=300",
    }).send(a.body);
  });

  r.post("/api/:service", async (req, res) => {
    const id = req.params.service;
    const service = isTool(id) ? services.get(id) : null;
    if (!service) return res.status(404).json({ status: "error", error: "unknown_service", services: TOOL_IDS });
    const ip = req.ip || "unknown";
    if (!allow(`web|${id}|${ip}`)) {
      return res.status(429).set("Retry-After", "60").json(failure(service, "rate_limited", "too many checks this minute"));
    }
    try {
      const params = req.body && typeof req.body === "object" && !Array.isArray(req.body) ? req.body : {};
      const [status, body] = await service.handle(params,
                                                  { callerId: callerIdOf(ip), web: true });
      return res.status(status).set("Cache-Control", "no-store").json(body);
    } catch {
      return res.status(500).json(failure(service, "internal_error", "the check failed; try again"));
    }
  });

  // Mounted at /tools, so "/tools" and "/tools/" both arrive here as "/": the URL tells them apart.
  r.get("/", (req, res) => (req.originalUrl.split("?")[0] === "/tools"
    ? res.redirect(301, "/tools/") : html(res, 200, renderIndex("en", opts))));
  r.get("/:a", (req, res) => {
    const a = req.params.a;
    if (isLang(a)) return res.redirect(301, `/tools/${a}/`);
    if (a === "en") return res.redirect(301, "/tools/");
    if (isTool(a)) return html(res, 200, renderTool("en", a, opts));
    return html(res, 404, renderNotFound("en", opts));
  });
  r.get("/:a/", (req, res) => {
    const a = req.params.a;
    if (isLang(a)) return html(res, 200, renderIndex(a, opts));
    if (a === "en") return res.redirect(301, "/tools/");
    if (isTool(a)) return res.redirect(301, `/tools/${a}`);
    return html(res, 404, renderNotFound("en", opts));
  });
  r.get("/:lang/:id", (req, res) => {
    const { lang, id } = req.params;
    if (lang === "en" && isTool(id)) return res.redirect(301, `/tools/${id}`);
    if (isLang(lang) && isTool(id)) return html(res, 200, renderTool(lang, id, opts));
    return html(res, 404, renderNotFound(isLang(lang) ? lang : "en", opts));
  });
  r.use((_req, res) => html(res, 404, renderNotFound("en", opts)));
  app.use("/tools", r);
}
