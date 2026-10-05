import { test } from "node:test";
import assert from "node:assert/strict";
import { createApp } from "../src/app.js";
import { HEARTH_TOOLS } from "../src/hearth.js";
import { openapiDocument } from "../src/x402.js";

async function serve(opts = {}) {
  const app = createApp(opts);
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  return { call: (path, init) => fetch(base + path, init), close: () => new Promise((r) => server.close(r)) };
}
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const IDS = Object.keys(HEARTH_TOOLS);
const paywall = {
  paths: IDS.map((id) => `POST /x402/${id}`), price: "$0.001", network: "eip155:8453",
  payTo: "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
  middleware: (req, res, next) =>
    req.path.startsWith("/x402/") && !req.headers["payment-signature"] ? res.status(402).json({ x402Version: 2 }) : next(),
};
const paid = { "payment-signature": "test", "content-type": "application/json" };

function fakeHearth(respond) {
  const calls = [];
  return { calls, fetchImpl: async (url, init) => { calls.push({ url, headers: init.headers, body: JSON.parse(init.body) }); return respond(); } };
}

test("without a hearth key the HESTIA agents are not sold", async () => {
  const { call, close } = await serve({ paywall });
  try {
    const m = await (await call("/a2mcp")).json();
    for (const id of IDS) assert.ok(!m.services.some((s) => s.id === id), id);
  } finally { await close(); }
});

test("a HESTIA twin is never free: the free route answers 402 and never reaches the hearth", async () => {
  const hearth = fakeHearth(() => { throw new Error("must not be called"); });
  const { call, close } = await serve({ paywall, hearthApiKey: "k", fetchImpl: hearth.fetchImpl });
  try {
    for (const id of IDS) {
      const res = await call(`/a2mcp/${id}`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      assert.equal(res.status, 402, id);
    }
    assert.equal(hearth.calls.length, 0);
  } finally { await close(); }
});

test("a paid call buys from the hearth directly, says what the buyer paid, and returns the signed answer", async () => {
  const answer = { ok: true, result: { verdict: "invalid", diagnosis: { explains: "re-sign" } }, provider_pubkey: "pk", signature: "sig" };
  const hearth = fakeHearth(() => json(200, answer));
  const { call, close } = await serve({ paywall, hearthApiKey: "seller-key", hearthUrl: "https://hearth.example/", publicUrl: "https://gw.example", fetchImpl: hearth.fetchImpl });
  try {
    const example = HEARTH_TOOLS["x402-check"].example;
    const res = await call("/x402/x402-check", { method: "POST", headers: paid, body: JSON.stringify(example) });
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.deepEqual(body.result, answer.result);
    assert.equal(body.signature, "sig");
    assert.equal(body.provider_pubkey, "pk");
    const sent = hearth.calls[0];
    assert.equal(sent.url, "https://hearth.example/ai-market/v2/invoke");
    assert.equal(sent.headers["x-api-key"], "seller-key");
    assert.equal(sent.headers["x-aimarket-hub-charged"], "0.003");
    assert.deepEqual(sent.body, { capability_id: "x402.authorization.check@v1", input: example });
  } finally { await close(); }
});

test("mcp-diff takes two tools/list results, as lists or {tools}, and nothing it does not need", async () => {
  const hearth = fakeHearth(() => json(200, { ok: true, result: { verdict: "suspicious" } }));
  const { call, close } = await serve({ paywall, hearthApiKey: "k", fetchImpl: hearth.fetchImpl });
  try {
    const old = [{ name: "add", description: "Adds." }];
    const res = await call("/x402/mcp-diff", { method: "POST", headers: paid, body: JSON.stringify({ old: { tools: old }, new: old, extra: "x" }) });
    assert.equal(res.status, 200);
    assert.deepEqual(hearth.calls[0].body, { capability_id: "mcp.tools.diff@v1", input: { old, new: old } });
  } finally { await close(); }
});

test("an input the agent cannot use is refused as input_required (400, not settled) before the hearth is called", async () => {
  const hearth = fakeHearth(() => { throw new Error("must not be called"); });
  const { call, close } = await serve({ paywall, hearthApiKey: "k", fetchImpl: hearth.fetchImpl });
  try {
    for (const [id, body] of [["x402-check", { requirements: {} }], ["mcp-diff", { old: [] }],
      ["mcp-diff", { old: new Array(501).fill({ name: "x" }), new: [] }]]) {
      const res = await call(`/x402/${id}`, { method: "POST", headers: paid, body: JSON.stringify(body) });
      assert.equal(res.status, 400, id);
      assert.equal((await res.json()).status, "input_required", id);
    }
    assert.equal(hearth.calls.length, 0);
  } finally { await close(); }
});

test("a refusal or an unreachable hearth is not settled: the buyer pays nothing", async () => {
  for (const [respond, status] of [[() => json(400, { detail: "bad input" }), 400], [() => json(503, { detail: "x" }), 502],
    [() => { throw new Error("down"); }, 502]]) {
    const hearth = fakeHearth(respond);
    const { call, close } = await serve({ paywall, hearthApiKey: "k", fetchImpl: hearth.fetchImpl });
    try {
      const res = await call("/x402/mcp-diff", { method: "POST", headers: paid, body: JSON.stringify({ old: [], new: [] }) });
      assert.equal(res.status, status);
    } finally { await close(); }
  }
});

test("both are in the OpenAPI the x402 indexers read, at the agents' own price", () => {
  const doc = openapiDocument({ publicUrl: "https://modelmarket.dev", payTo: paywall.payTo, serviceIds: IDS });
  for (const id of IDS) {
    const op = doc.paths[`/x402/${id}`]?.post;
    assert.ok(op, id);
    assert.match(JSON.stringify(op), /0\.003/, id);
  }
});
