import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createApp } from "../src/app.js";
import { HEARTH_TOOLS } from "../src/hearth.js";
import { EXAMPLES } from "../src/web/examples.js";
import { LANGS, STRINGS } from "../src/web/i18n/index.js";
import { ASSETS, TOOL_IDS, pathFor } from "../src/web/pages.js";

async function serve(opts = {}) {
  // A hearth key by default: without one the two HESTIA agents, and their pages, do not exist.
  const app = createApp({ publicUrl: "https://modelmarket.dev", hearthApiKey: "k", hearthUrl: "https://hearth.invalid", ...opts });
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  return { call: (path, init) => fetch(base + path, { redirect: "manual", ...init }), close: () => new Promise((r) => server.close(r)) };
}
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const post = (body, headers = {}) => ({ method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) });
const hearthAnswer = { ok: true, result: { verdict: "invalid" }, provider_pubkey: "pk", signature: "sig" };
function fakeUpstream() {
  const calls = [];
  return {
    calls,
    fetchImpl: async (url, init) => {
      calls.push({ url: String(url), headers: init.headers, body: JSON.parse(init.body) });
      if (String(url).includes("/api/v1/check")) return json(200, { type: "histor.check/v1", match: "not-listed" });
      return json(200, hearthAnswer);
    },
  };
}

/** Every leaf path of an object, arrays by index: the shape a translation has to match. */
function shape(value, path = "", out = []) {
  if (Array.isArray(value)) value.forEach((v, i) => shape(v, `${path}[${i}]`, out));
  else if (value && typeof value === "object") for (const k of Object.keys(value)) shape(value[k], `${path}.${k}`, out);
  else out.push(path);
  return out;
}

test("every language carries exactly the English keys, and none is left empty", () => {
  const reference = shape(STRINGS.en).sort();
  for (const lang of LANGS) {
    assert.deepEqual(shape(STRINGS[lang]).sort(), reference, lang);
    for (const p of shape(STRINGS[lang])) {
      const v = p.split(/\.|\[|\]/).filter(Boolean).reduce((o, k) => o[k], STRINGS[lang]);
      assert.ok(typeof v === "string" && v.trim(), `${lang}${p} is empty`);
    }
    assert.ok(STRINGS[lang].ui.agentsLead.includes("{price}"), `${lang} agentsLead keeps the price slot`);
  }
});

test("every page is served in every language with its canonical, alternates and structured data", async () => {
  const { call, close } = await serve();
  try {
    for (const lang of LANGS) {
      for (const id of ["", ...TOOL_IDS]) {
        const path = pathFor(lang, id);
        const res = await call(path);
        assert.equal(res.status, 200, path);
        assert.match(res.headers.get("content-security-policy"), /script-src 'self'/);
        assert.equal(res.headers.get("x-frame-options"), "DENY");
        const html = await res.text();
        assert.match(html, new RegExp(`<link rel="canonical" href="https://modelmarket.dev${path}">`), path);
        for (const l of LANGS) assert.ok(html.includes(`href="https://modelmarket.dev${pathFor(l, id)}"`), `${path} → ${l}`);
        assert.ok(html.includes('hreflang="x-default"'), path);
        assert.equal(html.match(/<h1[ >]/g).length, 1, `${path} has one h1`);
        const ld = html.match(/<script type="application\/ld\+json">(.*?)<\/script>/s);
        assert.ok(JSON.parse(ld[1])["@context"], path);
        // An Offer makes Google read the page as a product and ask for ratings and reviews no free tool has.
        assert.ok(!ld[1].includes('"Offer"'), `${path} carries no Offer`);
        // Each data block closes once: nothing inside can end the <script> early.
        assert.equal(html.match(/<script/g).length, html.match(/<\/script>/g).length, path);
        if (id) {
          const data = JSON.parse(html.match(/<script type="application\/json" id="tool-data">(.*?)<\/script>/s)[1]);
          assert.equal(data.tool, id);
          assert.equal(data.api, `/tools/api/${id}`);
          assert.deepEqual(data.example, EXAMPLES[id]);
        }
      }
    }
  } finally { await close(); }
});

test("one URL per page: the other spellings redirect to it, unknown pages are a 404 page", async () => {
  const { call, close } = await serve();
  try {
    const redirects = {
      "/tools": "/tools/", "/tools/ru": "/tools/ru/", "/tools/en": "/tools/", "/tools/en/": "/tools/",
      "/tools/x402-check/": "/tools/x402-check", "/tools/en/mcp-diff": "/tools/mcp-diff",
    };
    for (const [from, to] of Object.entries(redirects)) {
      const res = await call(from);
      assert.equal(res.status, 301, from);
      assert.equal(res.headers.get("location"), to, from);
    }
    for (const path of ["/tools/nope", "/tools/ru/nope", "/tools/xx/x402-check", "/tools/a/b/c"]) {
      const res = await call(path);
      assert.equal(res.status, 404, path);
      assert.match(res.headers.get("content-type"), /text\/html/);
    }
  } finally { await close(); }
});

test("sitemap lists every page in every language with alternates; robots names it", async () => {
  const { call, close } = await serve();
  try {
    const xml = await (await call("/tools/sitemap.xml")).text();
    const locs = [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((m) => m[1]);
    assert.equal(locs.length, LANGS.length * (TOOL_IDS.length + 1));
    for (const loc of locs) assert.equal((await call(loc.replace("https://modelmarket.dev", ""))).status, 200, loc);
    const robots = await (await call("/tools/robots.txt")).text();
    assert.match(robots, /^User-agent: \*\nAllow: \//);
    assert.match(robots, /Sitemap: https:\/\/modelmarket.dev\/tools\/sitemap.xml/);
  } finally { await close(); }
});

test("assets: the versioned URL the pages link is cached for good, anything else is a 404", async () => {
  const { call, close } = await serve();
  try {
    for (const [name, a] of Object.entries(ASSETS)) {
      const res = await call(`/tools/assets/${name}?v=${a.version}`);
      assert.equal(res.status, 200);
      assert.match(res.headers.get("cache-control"), /immutable/);
      assert.match((await (await call(pathFor("en", "mcp-diff"))).text()), new RegExp(`${name}\\?v=${a.version}`));
    }
    assert.equal((await call("/tools/assets/tools.js")).headers.get("cache-control"), "public, max-age=300");
    assert.equal((await call("/tools/assets/..%2Fapp.js")).status, 404);
    assert.equal((await call("/tools/assets/x.js")).status, 404);
  } finally { await close(); }
});

test("the page's script never writes HTML, and no page quotes an injected instruction", async () => {
  const js = readFileSync(new URL("../src/web/assets/tools.js", import.meta.url), "utf8");
  assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(js.replace(/^\/\/.*$/gm, "")));
  const { call, close } = await serve();
  try {
    for (const lang of LANGS) {
      for (const id of TOOL_IDS) {
        const html = await (await call(pathFor(lang, id))).text();
        assert.ok(!/ignore (all |the )?(previous|prior|above) instructions/i.test(html), `${lang}/${id}`);
      }
    }
  } finally { await close(); }
});

test("the free WARDEN scan answers the page's example: one tool blocked, one allowed", async () => {
  const { call, close } = await serve();
  try {
    const res = await call("/tools/api/warden-scan", post({ tools: EXAMPLES["warden-scan"].tools }));
    assert.equal(res.status, 200);
    assert.equal(res.headers.get("cache-control"), "no-store");
    const body = await res.json();
    assert.equal(body.verdict.allow, false);
    assert.deepEqual(body.verdict.blockedTools, ["read_note"]);
    assert.deepEqual(body.verdict.allowedTools, ["search_notes"]);
  } finally { await close(); }
});

test("the page's examples are what the agents accept", () => {
  assert.ok(HEARTH_TOOLS["x402-check"].build({ ...EXAMPLES["x402-check"].payment, requirements: EXAMPLES["x402-check"].requirements, now: 1 }));
  assert.ok(HEARTH_TOOLS["mcp-diff"].build(EXAMPLES["mcp-diff"]));
});

test("the HESTIA agents are free on the page only: the hearth is told 0 was charged, under a shared budget", async () => {
  const up = fakeUpstream();
  const { call, close } = await serve({ hearthApiKey: "k", hearthUrl: "https://hearth.example", fetchImpl: up.fetchImpl,
                                        freeHearthPerMinute: 3, webPerMinute: 100 });
  try {
    // The agent door stays paid.
    assert.equal((await call("/a2mcp/x402-check", post(EXAMPLES["x402-check"].payment))).status, 402);
    assert.equal(up.calls.length, 0);
    const ex = { ...EXAMPLES["x402-check"].payment, requirements: EXAMPLES["x402-check"].requirements };
    const res = await call("/tools/api/x402-check", post(ex));
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.deepEqual(body.result, hearthAnswer.result);
    assert.equal(body.signature, "sig");
    assert.equal(up.calls[0].url, "https://hearth.example/ai-market/v2/invoke");
    assert.equal(up.calls[0].headers["x-aimarket-hub-charged"], "0");
    assert.equal(up.calls[0].body.capability_id, "x402.authorization.check@v1");
    // One budget for both agents: two more pass, the fourth is refused before the hearth.
    assert.equal((await call("/tools/api/mcp-diff", post(EXAMPLES["mcp-diff"]))).status, 200);
    assert.equal((await call("/tools/api/mcp-diff", post(EXAMPLES["mcp-diff"]))).status, 200);
    const busy = await call("/tools/api/x402-check", post(ex));
    assert.equal(busy.status, 429);
    assert.equal((await busy.json()).error, "free_capacity");
    assert.equal(up.calls.length, 3);
    // Missing input is a question, not a hearth call.
    assert.equal((await (await call("/tools/api/mcp-diff", post({}))).json()).status, "input_required");
  } finally { await close(); }
});

test("each address gets its own per-tool budget on the page", async () => {
  const { call, close } = await serve({ webPerMinute: 2 });
  try {
    const scan = () => call("/tools/api/warden-scan", post({ tools: EXAMPLES["warden-scan"].tools }));
    assert.equal((await scan()).status, 200);
    assert.equal((await scan()).status, 200);
    const third = await scan();
    assert.equal(third.status, 429);
    assert.equal((await third.json()).error, "rate_limited");
    // Another address is another bucket.
    const other = await call("/tools/api/warden-scan", { ...post({ tools: EXAMPLES["warden-scan"].tools }), headers: { "content-type": "application/json", "x-forwarded-for": "203.0.113.9" } });
    assert.equal(other.status, 200);
  } finally { await close(); }
});

test("the page's HISTOR lookup goes to HISTOR; unknown tools and array bodies are refused", async () => {
  const up = fakeUpstream();
  const { call, close } = await serve({ fetchImpl: up.fetchImpl, hearthApiKey: "" });
  try {
    const res = await call("/tools/api/histor-check", post({ endpoint: "https://modelmarket.dev/mcp" }));
    assert.equal(res.status, 200);
    assert.equal((await res.json()).check.match, "not-listed");
    assert.match(up.calls[0].url, /\/api\/v1\/check$/);
    assert.deepEqual(up.calls[0].body, { endpoint: "https://modelmarket.dev/mcp" });
    assert.equal((await call("/tools/api/weather-now", post({}))).status, 404);
    assert.equal((await (await call("/tools/api/warden-scan", { method: "POST", headers: { "content-type": "application/json" }, body: "[1]" })).json()).status, "input_required");
    // Without a hearth key the two agents have no page and no page API.
    assert.equal((await call("/tools/api/mcp-diff", post(EXAMPLES["mcp-diff"]))).status, 404);
    assert.equal((await call("/tools/mcp-diff")).status, 404);
  } finally { await close(); }
});


test("IndexNow's key is served under /tools/, and a Search Console token lands in every page's head", async () => {
  const key = readFileSync(new URL("../src/web/indexnow-key.txt", import.meta.url), "utf8").trim();
  assert.match(key, /^[a-f0-9]{32}$/);
  const { call, close } = await serve({ siteVerification: "abc_DEF-123" });
  try {
    const res = await call(`/tools/${key}.txt`);
    assert.equal(res.status, 200);
    assert.equal((await res.text()).trim(), key);
    for (const path of ["/tools/", "/tools/ru/mcp-diff"]) {
      assert.match(await (await call(path)).text(), /<meta name="google-site-verification" content="abc_DEF-123">/);
    }
  } finally { await close(); }
  const plain = await serve();
  try {
    assert.ok(!(await (await plain.call("/tools/")).text()).includes("google-site-verification"));
  } finally { await plain.close(); }
});
