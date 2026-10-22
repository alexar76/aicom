import { test } from "node:test";
import assert from "node:assert/strict";
import { createApp } from "../src/app.js";
import { shareBelow, SNAPSHOT, toolListCost, workerCounter } from "../src/toolcost.js";
import { countTools } from "../src/toolcount.js";
import { renderTool } from "../src/web/pages.js";

// Counts tiktoken 0.12 gives for these three tools (o200k_base, disallowed_special=()), the way
// histor/scripts/tool_list_tokens.py counts: per tool and for the list as listed.
const FIXTURE = [
  { name: "search_notes", description: "Searches your notes by keyword and returns matching titles.",
    annotations: { readOnlyHint: true },
    inputSchema: { type: "object", properties: { query: { type: "string", description: "words to look for" } }, required: ["query"] } },
  { name: "translate", description: "Übersetzt Text — 翻译文本. Marker <|endoftext|> stays text.",
    inputSchema: { type: "object", properties: { text: { type: "string" }, to: { type: "string", enum: ["de", "zh", "ru"] } } } },
  { name: "ping" },
];

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const post = (body) => ({ method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

/** A HISTOR that knows one remote server and one package, and counts what it is asked. */
function fakeHistor() {
  const calls = [];
  const servers = [
    { id: "a1", name: "io.github.example/notes", endpoint: "https://mcp.example.com/mcp", transport: "streamable-http",
      toolCount: 3, toolSetDigest: "sha256-AAA/x=", lastObserved: "2026-10-18T21:59:06Z" },
    { id: "b2", name: "io.github.example/pkg", endpoint: "npm:@example/pkg", transport: "stdio",
      toolCount: 3, toolSetDigest: "sha256-AAA/x=", lastObserved: "2026-10-18T10:00:00Z" },
    { id: "c3", name: "io.github.example/silent", endpoint: "https://silent.example.com/mcp", transport: "streamable-http",
      toolCount: null, toolSetDigest: null, lastObserved: null, lastStatus: "exited" },
  ];
  const fetchImpl = async (url) => {
    const u = new URL(String(url));
    calls.push(u.pathname + u.search);
    if (u.pathname === "/api/v1/servers") {
      const q = u.searchParams.get("q").toLowerCase();
      const hit = servers.filter((s) => s.endpoint.toLowerCase().includes(q) || s.name.toLowerCase().includes(q));
      return json(200, { total: hit.length, servers: hit });
    }
    if (u.pathname === `/api/v1/toolsets/${encodeURIComponent("sha256-AAA/x=")}`) return json(200, FIXTURE);
    return json(404, { detail: "unknown" });
  };
  return { calls, fetchImpl };
}

async function serve(opts = {}) {
  const app = createApp({ publicUrl: "https://modelmarket.dev", historUrl: "https://histor.test", ...opts });
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  return { call: (path, init) => fetch(base + path, init), close: () => new Promise((r) => server.close(r)) };
}

test("the count is tiktoken's: per tool {name, description, input_schema}, special-token text as text", () => {
  const c = countTools(FIXTURE);
  assert.deepEqual(c.per.map((t) => t.tokens), [47, 60, 14]);
  assert.equal(c.tokens, 121);
  assert.equal(c.listedTokens, 122);
  assert.equal(c.tools, 3);
});

test("placement follows the snapshot: its own percentiles come back, and it only grows", () => {
  assert.equal(Math.round(shareBelow("package", SNAPSHOT.package.median) * 100), 50);
  assert.equal(Math.round(shareBelow("package", SNAPSHOT.package.p90) * 100), 90);
  assert.equal(Math.round(shareBelow("remote", SNAPSHOT.remote.median) * 100), 50);
  let last = -1;
  for (const n of [1, 50, 500, 1_000, 1_272, 2_000, 9_000, 40_000, 120_000, 400_000, 1_000_000]) {
    const s = shareBelow("package", n);
    assert.ok(s >= last && s >= 0 && s <= 1, `${n}: ${s}`);
    last = s;
  }
  assert.equal(shareBelow("package", 0), 0);
  assert.equal(shareBelow("package", 10_000_000), 1);
});

test("a pasted list is counted on the page and for agents, with money and the heaviest tools first", async () => {
  const { call, close } = await serve({ fetchImpl: async () => { throw new Error("a pasted list must not reach HISTOR"); } });
  try {
    for (const path of ["/tools/api/tool-list-cost", "/a2mcp/tool-list-cost"]) {
      const res = await call(path, post({ tools: { tools: FIXTURE } }));
      assert.equal(res.status, 200, path);
      const b = await res.json();
      assert.equal(b.status, "ok");
      assert.equal(b.source, "pasted");
      assert.equal(b.tokens, 121);
      assert.deepEqual(b.heaviest.map((t) => t.name), ["translate", "search_notes", "ping"]);
      assert.equal(b.per_1000_requests_usd.mid, 0.24);
      assert.ok(b.compared.package.share_shorter < 0.2);
      assert.equal(b.compared.package.servers, 18_204);
    }
    const bad = await call("/tools/api/tool-list-cost", post({ tools: [{ description: "no name" }] }));
    assert.equal(bad.status, 400);
    assert.equal((await bad.json()).error, "bad_tools");
  } finally { await close(); }
});

test("a lookup asks HISTOR, never the server, and keeps the count; the badge reads the same count", async () => {
  const h = fakeHistor();
  const { call, close } = await serve({ fetchImpl: h.fetchImpl });
  try {
    const res = await call("/tools/api/tool-list-cost", post({ server: "https://mcp.example.com/mcp" }));
    assert.equal(res.status, 200);
    const b = await res.json();
    assert.equal(b.found, true);
    assert.equal(b.tokens, 121);
    assert.equal(b.server.page, "https://histor.test/s/a1");
    assert.ok(h.calls.every((c) => c.startsWith("/api/v1/")), "only HISTOR's API is asked");
    const before = h.calls.length;
    const badge = await call(`/tools/badge/tool-list-cost?server=${encodeURIComponent("https://mcp.example.com/mcp")}`);
    assert.equal(badge.status, 200);
    assert.deepEqual(await badge.json(), { schemaVersion: 1, label: "tool list", message: "121 tokens", color: "2f9e77", cacheSeconds: 3600 });
    assert.match(badge.headers.get("cache-control"), /max-age=3600/);
    assert.equal(h.calls.length, before, "the hour-long cache answered the badge");

    // A bare package name finds the npm package; its tool set is the same digest, so no second download.
    const pkg = await (await call("/tools/api/tool-list-cost", post({ server: "@example/pkg" }))).json();
    assert.equal(pkg.server.endpoint, "npm:@example/pkg");
    assert.equal(h.calls.filter((c) => c.startsWith("/api/v1/toolsets/")).length, 1);

    const silent = await (await call("/tools/api/tool-list-cost", post({ server: "https://silent.example.com/mcp" }))).json();
    assert.deepEqual([silent.found, silent.known], [false, true]);
    // It says why there is no list, and where to read more.
    assert.equal(silent.server.lastStatus, "exited");
    assert.equal(silent.server.page, "https://histor.test/s/c3");

    // A host name typed without a scheme is the https endpoint.
    const bare = await (await call("/tools/api/tool-list-cost", post({ server: "mcp.example.com/mcp" }))).json();
    assert.equal(bare.server.endpoint, "https://mcp.example.com/mcp");
    // A registry name keeps its reverse-DNS reading.
    const reg = await (await call("/tools/api/tool-list-cost", post({ server: "io.github.example/notes" }))).json();
    assert.equal(reg.server.endpoint, "https://mcp.example.com/mcp");
    const unknown = await (await call("/tools/badge/tool-list-cost?server=https://nobody.example/mcp")).json();
    assert.equal(unknown.message, "not observed");
    assert.equal((await call("/tools/badge/tool-list-cost")).status, 400);
  } finally { await close(); }
});

test("lookups share one budget; a tool set too large to read is refused, not cut", async () => {
  const h = fakeHistor();
  const svc = toolListCost({ historUrl: "https://histor.test", fetchImpl: h.fetchImpl, timeoutMs: 1000, lookupsPerMinute: 1, now: () => 0 });
  assert.equal((await svc.handle({ server: "https://mcp.example.com/mcp" }))[0], 200);
  const [status, body] = await svc.handle({ server: "npm:@example/pkg" });
  assert.equal(status, 429);
  assert.equal(body.error, "free_capacity");

  const big = toolListCost({ historUrl: "https://histor.test", timeoutMs: 1000, now: () => 0, fetchImpl: async (url) => {
    const u = new URL(String(url));
    if (u.pathname === "/api/v1/servers") return json(200, { servers: [{ id: "z", name: "n", endpoint: "https://big.example/mcp", transport: "streamable-http", toolCount: 9, toolSetDigest: "d", lastObserved: "x" }] });
    return new Response("x".repeat(4_000_001), { status: 200 });
  } });
  const [s2, b2] = await big.handle({ server: "https://big.example/mcp" });
  assert.equal(s2, 422);
  assert.equal(b2.error, "too_large");
});

test("the page offers the badge line and no paid route, since this check is not sold", () => {
  const html = renderTool("en", "tool-list-cost", { origin: "https://modelmarket.dev" });
  assert.match(html, /img\.shields\.io\/endpoint\?url=https%3A%2F%2Fmodelmarket\.dev%2Ftools%2Fbadge%2Ftool-list-cost/);
  assert.ok(!html.includes("/x402/tool-list-cost"));
  assert.ok(html.includes("POST https://modelmarket.dev/a2mcp/tool-list-cost"));
});

test("a count that runs too long stops the worker, and the next count starts a fresh one", async () => {
  // The clock starts once the worker's table is ready: 300 ms is plenty for one tool and far
  // too little for 3,000 tools of 2,000 words each.
  const counter = workerCounter({ jobMs: 300 });
  const huge = Array.from({ length: 3_000 }, (_, i) => ({ name: `t${i}`, description: "word ".repeat(2_000) }));
  await assert.rejects(counter(huge), (e) => e.timeout === true);
  assert.equal((await counter([{ name: "ping" }])).tokens, 14);
  await assert.rejects(counter([{ description: "no name" }]), (e) => e === "tools[0] needs a string name");
});
