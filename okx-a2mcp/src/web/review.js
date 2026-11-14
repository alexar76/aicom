// Seller review before publication.
//
// Some sellers we list asked to see, before it is public, every text of ours that carries numbers
// about their services (YuTao, Insight and PriorSeal: alexar76/aimarket-hub#23, 2026-11-13). The
// gate on our side (scripts/seller_review.py) finds such passages in a draft and files them here;
// publishing stops until the seller has answered. This module is the seller's side of it: a page
// and an Atom/JSON feed behind a private link, where the seller reads each passage and answers
// "OK" or "object" (with a note). Nothing here is fetched from anywhere and nothing is sent: the
// seller pulls, in a browser or a feed reader.
//
// Storage is one JSON file (REVIEW_DATA_FILE, a docker volume): a handful of requests a month.
import express from "express";
import { createHash, timingSafeEqual } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const MAX_EXCERPT = 20_000;
const MAX_NOTE = 2_000;
const MAX_REQUESTS = 2_000;
const TOKEN_RE = /^[0-9a-f]{64}$/;
const ID_RE = /^[0-9a-f]{20}$/;
const DEFAULT_RULE = "We publish a passage only after you answer OK.";

/** The same id the gate computes: sha256 of "<seller>\n<excerpt>", first 20 hex digits. */
export function reviewId(seller, excerpt) {
  return createHash("sha256").update(`${seller}\n${excerpt}`, "utf8").digest("hex").slice(0, 20);
}

const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const clip = (v, n) => (typeof v === "string" ? v.slice(0, n) : "");

export function createReviewStore({ file = "", now = () => Date.now() } = {}) {
  let state = { requests: {} };
  if (file) {
    try {
      state = JSON.parse(readFileSync(file, "utf8"));
    } catch (e) {
      // A missing file is a first start. A broken one is not overwritten: the gateway refuses to
      // start, the deploy rolls back, and the file is still there to look at.
      if (e?.code !== "ENOENT") throw new Error(`review store ${file} is unreadable: ${e.message}`);
    }
    if (!state || typeof state.requests !== "object") state = { requests: {} };
  }
  function save() {
    if (!file) return;
    mkdirSync(dirname(file), { recursive: true });
    const tmp = `${file}.tmp`;
    writeFileSync(tmp, JSON.stringify(state, null, 1));
    renameSync(tmp, file);
  }
  return {
    get: (id) => state.requests[id] || null,
    list: (seller) => Object.values(state.requests).filter((r) => !seller || r.seller === seller)
      .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    create({ seller, excerpt, title = "", source = "", not_before = "" }) {
      const id = reviewId(seller, excerpt);
      const old = state.requests[id];
      if (old) return { record: old, created: false };
      if (Object.keys(state.requests).length >= MAX_REQUESTS) throw Object.assign(new Error("store full"), { status: 507 });
      const record = {
        id, seller, title: clip(title, 300), source: clip(source, 300), excerpt,
        created_at: iso(now()), not_before: clip(not_before, 40) || iso(now()),
        decision: null, decided_at: null, note: "", history: [],
      };
      state.requests[id] = record;
      save();
      return { record, created: true };
    },
    decide(id, seller, decision, note = "") {
      const r = state.requests[id];
      if (!r || r.seller !== seller) return null;
      const at = iso(now());
      Object.assign(r, { decision, decided_at: at, note: clip(note, MAX_NOTE) });
      r.history.push({ decision, at, note: r.note });
      save();
      return r;
    },
  };
}

function digestEq(a, b) {
  const x = createHash("sha256").update(String(a)).digest();
  const y = createHash("sha256").update(String(b)).digest();
  return timingSafeEqual(x, y);
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function status(r, nowMs) {
  if (r.decision === "ok") return `answered OK at ${r.decided_at}`;
  if (r.decision === "object") return `objected at ${r.decided_at}: not published until the text changes`;
  return Date.parse(r.not_before) > nowMs ? `waiting for your answer (we do not publish before ${r.not_before})`
    : "waiting for your answer";
}

function page(seller, records, token, nowMs) {
  const items = records.map((r) => `
<section id="r-${esc(r.id)}">
<h2>${esc(r.title || r.source || r.id)}</h2>
<p>Filed ${esc(r.created_at)}${r.source ? ` · ${esc(r.source)}` : ""} · <strong>${esc(status(r, nowMs))}</strong></p>
<blockquote>${r.excerpt.split(/\n{2,}/).map((p) => `<p>${esc(p)}</p>`).join("\n")}</blockquote>
<form method="post" action="/tools/review/${esc(token)}/${esc(r.id)}">
<label>Note (optional, ${MAX_NOTE} characters)<br><textarea name="note" rows="3" cols="80" maxlength="${MAX_NOTE}">${esc(r.note)}</textarea></label><br>
<button type="submit" name="decision" value="ok">OK to publish</button>
<button type="submit" name="decision" value="object">Object</button>
</form>
</section>`).join("\n<hr>\n");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Review before publication: ${esc(seller.name)}</title></head>
<body>
<h1>Review before publication: ${esc(seller.name)}</h1>
<p>Passages modelmarket.dev plans to publish that carry numbers about your services, filed by our
publishing check before anything goes out. ${esc(seller.rule || DEFAULT_RULE)} If a number changes,
the passage comes back here as a new entry. You can change an answer at any time before publication.</p>
<p>This page and its feeds (<a href="feed.xml">Atom</a>, <a href="feed.json">JSON</a>) are private to this link.
Please keep the link to yourself.</p>
${items || "<p>Nothing is waiting for you.</p>"}
</body></html>`;
}

function atom(seller, records, token, origin) {
  const base = `${origin}/tools/review/${token}/`;
  const updated = records[0]?.decided_at || records[0]?.created_at || "1970-01-01T00:00:00Z";
  const entries = records.map((r) => `<entry>
<id>urn:modelmarket:review:${r.id}</id>
<title>${esc(r.title || r.source || r.id)}</title>
<updated>${esc(r.decided_at || r.created_at)}</updated>
<link href="${esc(base)}#r-${esc(r.id)}"/>
<content type="text">${esc(`${r.excerpt}\n\nNot before: ${r.not_before}. Answer: ${r.decision || "none yet"}.`)}</content>
</entry>`).join("\n");
  return `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<id>urn:modelmarket:review:${esc(seller.id)}</id>
<title>Review before publication: ${esc(seller.name)}</title>
<updated>${esc(updated)}</updated>
<author><name>modelmarket.dev</name></author>
${entries}
</feed>`;
}

/**
 * Mount /tools/review before the app's body parser (forms post url-encoded bodies).
 * sellers: {id: {token, name, rule?}}; adminToken: what the gate sends as a Bearer token.
 * Without both, nothing is mounted and the paths stay 404.
 */
export function mountReview(app, { sellers = {}, adminToken = "", store, origin = "https://modelmarket.dev", now = () => Date.now() }) {
  const known = Object.entries(sellers)
    .filter(([, s]) => s && TOKEN_RE.test(String(s.token || "")))
    .map(([id, s]) => ({ id, token: s.token, name: s.name || id, rule: s.rule || "" }));
  if (!known.length || !adminToken || !store) return false;
  const bySellerId = new Map(known.map((s) => [s.id, s]));
  const byToken = (t) => (TOKEN_RE.test(t) ? known.find((s) => digestEq(s.token, t)) : undefined);
  const admin = (req) => {
    const h = req.get("authorization") || "";
    return h.startsWith("Bearer ") && digestEq(h.slice(7), adminToken);
  };
  const privateHeaders = {
    "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
  };
  const r = express.Router({ strict: true });
  const parsers = [express.urlencoded({ extended: false, limit: "16kb" }), express.json({ limit: "64kb" })];

  // Our side: the gate files passages and reads answers.
  r.post("/api/requests", parsers, (req, res) => {
    if (!admin(req)) return res.status(401).json({ error: "unauthorized" });
    const b = req.body && typeof req.body === "object" ? req.body : {};
    if (!bySellerId.has(b.seller)) return res.status(400).json({ error: "unknown_seller" });
    if (typeof b.excerpt !== "string" || !b.excerpt.trim() || b.excerpt.length > MAX_EXCERPT) {
      return res.status(400).json({ error: "bad_excerpt" });
    }
    if (b.not_before && Number.isNaN(Date.parse(b.not_before))) return res.status(400).json({ error: "bad_not_before" });
    try {
      const { record, created } = store.create(b);
      return res.status(created ? 201 : 200).set("Cache-Control", "no-store").json(record);
    } catch (e) {
      return res.status(e.status || 500).json({ error: "store_failed" });
    }
  });
  r.get("/api/requests/:id", (req, res) => {
    if (!admin(req)) return res.status(401).json({ error: "unauthorized" });
    const rec = ID_RE.test(req.params.id) ? store.get(req.params.id) : null;
    return rec ? res.set("Cache-Control", "no-store").json(rec) : res.status(404).json({ error: "not_found" });
  });
  r.get("/api/requests", (req, res) => {
    if (!admin(req)) return res.status(401).json({ error: "unauthorized" });
    return res.set("Cache-Control", "no-store").json({ requests: store.list(String(req.query.seller || "")) });
  });

  // The seller's side: page, feeds, answers.
  r.get("/:token", (req, res) => (byToken(req.params.token)
    ? res.redirect(301, `/tools/review/${req.params.token}/`) : res.status(404).set(privateHeaders).type("text/plain").send("not found")));
  r.get("/:token/", (req, res) => {
    const s = byToken(req.params.token);
    if (!s) return res.status(404).set(privateHeaders).type("text/plain").send("not found");
    return res.status(200).set(privateHeaders).type("html").send(page(s, store.list(s.id), req.params.token, now()));
  });
  r.get("/:token/feed.xml", (req, res) => {
    const s = byToken(req.params.token);
    if (!s) return res.status(404).set(privateHeaders).type("text/plain").send("not found");
    return res.set(privateHeaders).type("application/atom+xml").send(atom(s, store.list(s.id), req.params.token, origin));
  });
  r.get("/:token/feed.json", (req, res) => {
    const s = byToken(req.params.token);
    if (!s) return res.status(404).set(privateHeaders).json({ error: "not_found" });
    return res.set(privateHeaders).json({ seller: s.name, rule: s.rule || DEFAULT_RULE,
      requests: store.list(s.id).map(({ history, ...rest }) => rest) });
  });
  r.post("/:token/:id", parsers, (req, res) => {
    const s = byToken(req.params.token);
    if (!s || !ID_RE.test(req.params.id)) return res.status(404).set(privateHeaders).type("text/plain").send("not found");
    const decision = req.body?.decision;
    if (decision !== "ok" && decision !== "object") return res.status(400).set(privateHeaders).type("text/plain").send("decision must be ok or object");
    const rec = store.decide(req.params.id, s.id, decision, typeof req.body?.note === "string" ? req.body.note : "");
    if (!rec) return res.status(404).set(privateHeaders).type("text/plain").send("not found");
    if (req.is("application/json")) return res.set(privateHeaders).json(rec);
    return res.redirect(303, `/tools/review/${req.params.token}/#r-${rec.id}`);
  });
  app.use("/tools/review", r);
  return true;
}
