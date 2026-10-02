import { test } from "node:test";
import assert from "node:assert/strict";
import { createApp } from "../src/app.js";
import { HUB_TOOLS } from "../src/hub.js";

async function serve(opts = {}) {
  const app = createApp(opts);
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  return { call: (path, init) => fetch(base + path, init), close: () => new Promise((r) => server.close(r)) };
}
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const IDS = Object.keys(HUB_TOOLS);
const paywall = {
  paths: IDS.map((id) => `POST /x402/${id}`), price: "$0.001", network: "eip155:8453",
  payTo: "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
  middleware: (req, res, next) =>
    req.path.startsWith("/x402/") && !req.headers["payment-signature"] ? res.status(402).json({ x402Version: 2 }) : next(),
};
const paid = { "payment-signature": "test", "content-type": "application/json" };

function fakeHub(respond) {
  const calls = [];
  return { calls, fetchImpl: async (url, init) => { calls.push({ url, headers: init.headers, body: JSON.parse(init.body) }); return respond(); } };
}

test("without a hub key there are no hub twins", async () => {
  const { call, close } = await serve({ paywall });
  try {
    const m = await (await call("/a2mcp")).json();
    assert.deepEqual(m.services.map((s) => s.id).sort(), ["histor-check", "warden-scan"]);
  } finally { await close(); }
});

test("a hub twin is never free: the free route answers 402 and never reaches the hub", async () => {
  const hub = fakeHub(() => { throw new Error("must not be called"); });
  const { call, close } = await serve({ paywall, hubApiKey: "k", fetchImpl: hub.fetchImpl });
  try {
    for (const id of IDS) {
      const res = await call(`/a2mcp/${id}`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      assert.equal(res.status, 402, id);
    }
    const m = await (await call("/a2mcp")).json();
    const nearby = m.services.find((s) => s.id === "nearby-sensors");
    assert.equal(nearby.price, "x402 only, $0.03");
    assert.equal(nearby.x402.price, "$0.03");
    assert.equal(hub.calls.length, 0);
  } finally { await close(); }
});

test("a paid call buys the capability from the hub with the gateway's key and returns the receipt", async () => {
  const hub = fakeHub(() => json(200, { success: true, result: { temperature_c: 18.2 }, receipt: { sig: "r" }, price_usd: 0.001 }));
  const { call, close } = await serve({ paywall, hubApiKey: "secret-key", hubUrl: "https://hub.example/", fetchImpl: hub.fetchImpl });
  try {
    const res = await call("/x402/weather-now", { method: "POST", headers: paid, body: JSON.stringify({ latitude: 52.5, longitude: 13.4 }) });
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.deepEqual(body.result, { temperature_c: 18.2 });
    assert.deepEqual(body.receipt, { sig: "r" });
    assert.equal(hub.calls[0].url, "https://hub.example/ai-market/v2/invoke");
    assert.equal(hub.calls[0].headers["x-api-key"], "secret-key");
    assert.deepEqual(hub.calls[0].body, { product_id: "gaia.gateway", capability_id: "gaia.weather.read@v1",
      source_hub: "https://iot.modelmarket.dev", input: { latitude: 52.5, longitude: 13.4 } });
  } finally { await close(); }
});

test("a paid call the hub cannot serve, or with missing input, is not a 2xx (so it is not settled)", async () => {
  const hub = fakeHub(() => json(502, { success: false, error: "provider_unavailable" }));
  const { call, close } = await serve({ paywall, hubApiKey: "k", fetchImpl: hub.fetchImpl });
  try {
    const missing = await call("/x402/fair-random", { method: "POST", headers: paid, body: "{}" });
    assert.equal(missing.status, 400);
    assert.equal(hub.calls.length, 0, "missing input never reaches the hub");
    const failed = await call("/x402/nearby-sensors", { method: "POST", headers: paid, body: JSON.stringify({ latitude: 1, longitude: 2 }) });
    assert.equal(failed.status, 502);
    assert.deepEqual(hub.calls[0].body.input, { lat: 1, lon: 2, per_layer: true });
  } finally { await close(); }
});

test("the draw seed is passed whole, never cut", async () => {
  const hub = fakeHub(() => json(200, { success: true, result: { beta: "ab" }, receipt: null }));
  const { call, close } = await serve({ paywall, hubApiKey: "k", fetchImpl: hub.fetchImpl });
  try {
    const seed = "x".repeat(4096);
    assert.equal((await call("/x402/fair-random", { method: "POST", headers: paid, body: JSON.stringify({ seed }) })).status, 200);
    assert.equal(hub.calls[0].body.input.alpha, seed);
    const tooLong = await call("/x402/fair-random", { method: "POST", headers: paid, body: JSON.stringify({ seed: seed + "y" }) });
    assert.equal(tooLong.status, 400);
  } finally { await close(); }
});
