// ── tool-list-cost ──────────────────────────────────────────────────────────────────────
// What one MCP server's tool list costs a client: every definition rides along in each model
// request, whatever the user asks. Counted the way HISTOR counted 18,204 packages and 16,170
// remote servers on 2026-10-19 (histor/docs/tool-list-cost.md): per tool {name, description,
// input_schema} as compact JSON, tokenizer o200k_base. js-tiktoken gives the same count as
// tiktoken 0.12 (checked on 120 of HISTOR's tool sets, 2.6 M tokens, no difference).
//
// The list comes from the caller (a pasted tools/list) or from HISTOR's own observation of a
// server it watches; HISTOR is asked, the server itself never is. Pure counting otherwise.
import { Worker } from "node:worker_threads";
import { failure, inputRequired, ok } from "./a2mcp.js";
import { MAX_TOOLS } from "./toolcount.js";

const MAX_TOOLSET_BYTES = 4_000_000;  // the largest observed remote list is about 2 MB of JSON
const QUEUE = 8;                      // counts waiting for the worker; more are refused as busy
const SERVER_RE = /^[\x21-\x7e]{1,300}$/;

/**
 * The snapshot of 2026-10-19 (histor/docs/tool-list-tokens-2026-10-19.json): token counts at
 * which a known share of servers lists fewer. Between two points the share is interpolated on a
 * log scale, so a placement is "about", and the page says so.
 */
export const SNAPSHOT = Object.freeze({
  date: "2026-10-19",
  source: "https://github.com/alexar76/histor/blob/main/docs/tool-list-cost.md",
  package: { servers: 18_204, median: 1_272, p90: 8_361,
             points: [[0, 0], [1_000, 0.4295], [1_272, 0.5], [3_487, 0.75], [5_000, 0.8232], [8_361, 0.9],
                      [10_000, 0.9205], [39_612, 0.99], [50_000, 0.9937], [100_000, 0.9983], [304_780, 1]] },
  remote: { servers: 16_170, median: 1_328, p90: 7_425,
            points: [[0, 0], [1_000, 0.3731], [1_328, 0.5], [4_790, 0.75], [5_000, 0.7555], [7_425, 0.9],
                     [10_000, 0.9618], [22_294, 0.99], [50_000, 0.9976], [100_000, 0.9994], [547_935, 1]] },
});

/** Share of the snapshot's servers whose list is shorter than `n` tokens, 0..1. */
export function shareBelow(kind, n) {
  const pts = SNAPSHOT[kind].points;
  if (n <= 0) return 0;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    if (n <= x1) {
      const f = x0 === 0 ? n / x1 : Math.log(n / x0) / Math.log(x1 / x0);
      return y0 + (y1 - y0) * f;
    }
  }
  return 1;
}

// Input prices per million tokens the cost table uses: a small model, a mid-size model, and the
// mid-size model's price for a cached read (a twentieth). Same as the HISTOR note.
const PRICES = [["small", 0.10], ["mid", 2], ["mid_cached", 0.10]];
const CONTEXT = 200_000;

/** The answer for one count: totals, the heaviest tools, money, and where it sits in the snapshot. */
export function report(count) {
  const n = count.tokens;
  const heaviest = [...count.per].sort((a, b) => b.tokens - a.tokens).slice(0, 8);
  return {
    tokenizer: "o200k_base",
    counted_as: "per tool {name, description, input_schema} as compact JSON: what a client sends a model",
    tools: count.tools,
    tokens: n,
    tokens_as_listed: count.listedTokens,
    tokens_per_tool: count.tools ? Math.round(n / count.tools) : 0,
    heaviest,
    per_1000_requests_usd: Object.fromEntries(PRICES.map(([k, usd]) => [k, Math.round(n * usd / 1000 * 100) / 100])),
    prices_per_million_usd: Object.fromEntries(PRICES),
    context_share_200k: Math.round(n / CONTEXT * 10_000) / 10_000,
    compared: Object.fromEntries(["package", "remote"].map((k) => [k, {
      servers: SNAPSHOT[k].servers,
      median: SNAPSHOT[k].median,
      p90: SNAPSHOT[k].p90,
      share_shorter: Math.round(shareBelow(k, n) * 1000) / 1000,
      times_median: Math.round(n / SNAPSHOT[k].median * 10) / 10,
    }])),
    snapshot: { date: SNAPSHOT.date, source: SNAPSHOT.source },
  };
}

/** Badge colour by the share of packages with a shorter list. */
function colour(share) {
  if (share <= 0.5) return "2f9e77";
  if (share <= 0.9) return "c98a1b";
  if (share <= 0.99) return "e05d44";
  return "b60205";
}
const short = (n) => (n >= 10_000 ? `${Math.round(n / 1000)}k` : n >= 1_000 ? `${(n / 1000).toFixed(1)}k` : String(n));

/** Bounded insertion-order cache: the oldest entry goes first once it is full. */
function cache(size) {
  const m = new Map();
  return {
    get: (k) => m.get(k),
    set: (k, v) => {
      if (m.size >= size) m.delete(m.keys().next().value);
      m.set(k, v);
    },
  };
}

/**
 * Counting runs in a worker thread, started on the first count and stopped after half an hour
 * idle: the o200k table takes about 140 MB and seconds to build, and a list of 350,000 tokens
 * takes seconds that the gateway's other routes (paid x402 calls among them) must not wait for.
 * The worker says when its table is ready; from then each count has jobMs, and one that runs
 * past it stops the worker (the next count starts a fresh one).
 */
export function workerCounter({ idleMs = 1_800_000, jobMs = 15_000, startMs = 60_000 } = {}) {
  let worker = null;
  let ready = false;
  let starting = null;
  let idle = null;
  let keepWarm = false;
  let seq = 0;
  const pending = new Map();
  const arm = (id) => {
    const p = pending.get(id);
    if (!p || p.timer) return;
    p.timer = setTimeout(() => {
      pending.delete(id);
      stop();
      p.reject({ timeout: true });
    }, jobMs);
  };
  const settle = (id, fn) => {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    clearTimeout(p.timer);
    fn(p);
    if (!pending.size && worker && !keepWarm) {
      clearTimeout(idle);
      idle = setTimeout(stop, idleMs);
      idle.unref();
    }
  };
  function stop() {
    const w = worker;
    worker = null;
    ready = false;
    clearTimeout(starting);
    for (const id of [...pending.keys()]) settle(id, (p) => p.reject({ busy: true }));
    if (w) w.terminate();
  }
  function start() {
    const w = new Worker(new URL("./toolcount-worker.js", import.meta.url));
    w.on("message", (m) => {
      if (m && m.ready) {
        ready = true;
        clearTimeout(starting);
        for (const id of pending.keys()) arm(id);
        return;
      }
      settle(m.id, (p) => (m.error === undefined ? p.resolve(m.result) : p.reject(m.error)));
    });
    w.on("error", () => { if (worker === w) stop(); });
    w.on("exit", () => { if (worker === w) stop(); });
    // After the listeners: adding a "message" listener refs the port again. An idle worker must
    // not keep the process alive (tests, shutdown); a start or a count in flight holds a timer.
    w.unref();
    worker = w;
    starting = setTimeout(stop, startMs);
  }
  const count = (tools) => new Promise((resolve, reject) => {
    if (pending.size >= QUEUE) return reject({ busy: true });
    if (!worker) start();
    clearTimeout(idle);
    const id = ++seq;
    pending.set(id, { resolve, reject, timer: null });
    if (ready) arm(id);
    worker.postMessage({ id, tools });
  });
  /** Start the worker now and keep it: the server does this so a badge never waits for the table. */
  count.warm = () => {
    keepWarm = true;
    clearTimeout(idle);
    if (!worker) start();
  };
  return count;
}

/** What a failed count answers: bad input is the caller's, the rest is capacity. */
function countFailure(service, e) {
  if (typeof e === "string") return [400, failure(service, "bad_tools", e)];
  if (e && e.timeout) return [422, failure(service, "too_large", "this tool list took too long to count")];
  return [429, failure(service, "busy", "the counter is busy; retry shortly")];
}

export function toolListCost({ historUrl, fetchImpl, timeoutMs, lookupsPerMinute = 30, now = () => Date.now(),
                              counter = workerCounter(), warmCounter = false }) {
  if (warmCounter && counter.warm) counter.warm();
  // Lookups ask HISTOR twice; a shared budget keeps a crowd (or a badge flood) off it. A tool set
  // is content-addressed, so its count is kept by digest; a server's digest only for an hour.
  let window = { start: 0, count: 0 };
  const lookupAllowed = () => {
    const t = now();
    if (t - window.start >= 60_000) window = { start: t, count: 0 };
    if (window.count >= lookupsPerMinute) return false;
    window.count++;
    return true;
  };
  const byDigest = cache(2_000);
  const byServer = cache(5_000);
  const headers = { "user-agent": "okx-a2mcp/0.1 (+https://modelmarket.dev/tools/tool-list-cost)" };

  async function getJson(url, limit) {
    const res = await fetchImpl(url, { headers, signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) return { status: res.status };
    const text = await res.text();
    if (text.length > limit) return { status: 413 };
    return { status: 200, body: JSON.parse(text) };
  }

  /** HISTOR's record of a server: https endpoint, npm:/pypi: package, registry name or bare package. */
  async function resolve(server) {
    let q = server.trim();
    // A host name without a scheme (modelmarket.dev/mcp) is an https endpoint; a registry name
    // reads the other way round (io.github.owner/server) and a package has no dot before its slash.
    if (!/^[a-z]+:/i.test(q) && /^[^/@]+\.[a-z]{2,}(\/|$)/i.test(q) && !/^(io|com|dev|ai|net|org|app|co|me|sh|xyz)\./i.test(q)) {
      q = `https://${q}`;
    }
    const wanted = /^https:\/\//i.test(q) || /^(npm|pypi):/i.test(q) ? [q]
      : q.includes(".") && q.includes("/") && !q.startsWith("@") ? [q]
        : [`npm:${q}`, `pypi:${q}`, q];
    const found = await getJson(`${historUrl}/api/v1/servers?limit=50&q=${encodeURIComponent(q)}`, 2_000_000);
    if (found.status !== 200) throw { status: 502, code: "upstream_error", message: `HISTOR answered ${found.status}` };
    const list = Array.isArray(found.body?.servers) ? found.body.servers : [];
    const lc = wanted.map((w) => w.toLowerCase());
    const hits = list.filter((s) => lc.includes(String(s.endpoint).toLowerCase()) || lc.includes(String(s.name).toLowerCase()));
    const observed = hits.filter((s) => s.toolSetDigest && s.toolCount > 0)
      .sort((a, b) => String(b.lastObserved || "").localeCompare(String(a.lastObserved || "")));
    return { known: hits.length > 0, target: observed[0] || null, listed: hits[0] || null };
  }

  async function lookup(server) {
    const hit = byServer.get(server);
    if (hit && now() - hit.at < 3_600_000) return hit.value;
    if (!lookupAllowed()) throw { status: 429, code: "free_capacity", message: "lookups are at capacity this minute; retry shortly" };
    const { known, target, listed } = await resolve(server);
    let value;
    if (!target) {
      value = { known, target: null, listed };
    } else {
      let count = byDigest.get(target.toolSetDigest);
      if (!count) {
        const set = await getJson(`${historUrl}/api/v1/toolsets/${encodeURIComponent(target.toolSetDigest)}`, MAX_TOOLSET_BYTES);
        if (set.status === 413) throw { status: 422, code: "too_large", message: "this server's tool list is larger than the counter reads" };
        if (set.status !== 200) throw { status: 502, code: "upstream_error", message: `HISTOR answered ${set.status}` };
        const tools = Array.isArray(set.body) ? set.body : Array.isArray(set.body?.tools) ? set.body.tools : [];
        try {
          count = await counter(tools);
        } catch (e) {
          const [status, body] = countFailure(service, e);
          throw { status, code: body.error, message: body.message };
        }
        byDigest.set(target.toolSetDigest, count);
      }
      value = { known, target, count };
    }
    byServer.set(server, { at: now(), value });
    return value;
  }

  const service = {
    id: "tool-list-cost",
    methods: ["POST"],
    fields: [
      { name: "tools", type: "array", required: false,
        description: `the server's tools/list result: [{name, description, inputSchema, ...}], at most ${MAX_TOOLS} (send this or server)` },
      { name: "server", type: "string", required: false,
        description: "a server HISTOR observes: https endpoint, npm:<package>, pypi:<package> or registry name (send this or tools)" },
    ],
  };

  service.handle = async (params) => {
    const raw = Array.isArray(params.tools) ? params.tools : Array.isArray(params.tools?.tools) ? params.tools.tools : null;
    const server = typeof params.server === "string" ? params.server.trim() : "";
    if (raw) {
      try {
        return [200, ok(service, { source: "pasted", ...report(await counter(raw)) })];
      } catch (e) {
        return countFailure(service, e);
      }
    }
    if (!server) return [200, inputRequired(service, "send tools (a tools/list result) or server (a server HISTOR observes)")];
    if (!SERVER_RE.test(server)) return [400, failure(service, "bad_server", "server must be an https URL, npm:<package>, pypi:<package> or a registry name")];
    let found;
    try {
      found = await lookup(server);
    } catch (e) {
      if (e && e.status) return [e.status, failure(service, e.code, e.message)];
      return [502, failure(service, "upstream_unreachable", "HISTOR did not answer; try again")];
    }
    if (!found.target) {
      const l = found.listed;
      return [200, ok(service, {
        source: "histor", found: false, known: found.known,
        note: found.known ? "HISTOR lists this server but holds no tool list for it yet" : "HISTOR has no server by this name or address",
        // Why there is no list: HISTOR's last outcome for it (exited, auth, timeout, …) and its page.
        ...(l ? { server: { name: l.name, endpoint: l.endpoint, transport: l.transport, lastStatus: l.lastStatus || null,
                            lastAttempt: l.lastAttempt || null, page: `${historUrl}/s/${encodeURIComponent(l.id)}` } } : {}),
      })];
    }
    const t = found.target;
    return [200, ok(service, {
      source: "histor", found: true,
      server: { name: t.name, endpoint: t.endpoint, transport: t.transport, lastObserved: t.lastObserved,
                toolSetDigest: t.toolSetDigest, page: `${historUrl}/s/${encodeURIComponent(t.id)}` },
      ...report(found.count),
    })];
  };

  /** shields.io endpoint JSON for a README badge; null when HISTOR holds no list for the server. */
  service.badge = async (server) => {
    if (!SERVER_RE.test(server)) return { status: 400, body: { schemaVersion: 1, label: "tool list", message: "bad server", color: "6b7280", isError: true } };
    let found;
    try {
      found = await lookup(server);
    } catch (e) {
      const msg = e && e.status === 429 ? "busy, retry" : "lookup failed";
      return { status: 200, body: { schemaVersion: 1, label: "tool list", message: msg, color: "6b7280", isError: true, cacheSeconds: 300 } };
    }
    if (!found.target) {
      return { status: 200, body: { schemaVersion: 1, label: "tool list", message: "not observed", color: "6b7280", cacheSeconds: 3600 } };
    }
    const n = found.count.tokens;
    const kind = found.target.transport === "stdio" ? "package" : "remote";
    return { status: 200, body: { schemaVersion: 1, label: "tool list", message: `${short(n)} tokens`,
                                   color: colour(shareBelow(kind, n)), cacheSeconds: 3600 } };
  };

  return service;
}
