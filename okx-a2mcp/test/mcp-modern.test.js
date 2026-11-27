// The /tools/mcp servers on MCP 2026-07-28, beside the handshake they have always spoken. A
// 2026-07-28 client sends no `initialize`: every request names its protocol version and
// capabilities in `_meta` and mirrors version, method and tool name into HTTP headers. What the
// specification makes a server reject is pinned here with the status and error code it assigns.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createApp } from "../src/app.js";
import { decodeHeaderValue, isModern, HEADER_MISMATCH, UNSUPPORTED_PROTOCOL_VERSION } from "../src/mcp/modern.js";

const V = "2026-07-28";
const META = {
  "io.modelcontextprotocol/protocolVersion": V,
  "io.modelcontextprotocol/clientInfo": { name: "node-test-modern", version: "1" },
  "io.modelcontextprotocol/clientCapabilities": {},
};
const EVERY = [V, "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

async function serve() {
  const fetchImpl = async (url, init = {}) => (String(url).startsWith("https://hub.test/")
    ? json(200, { success: true, result: { echo: JSON.parse(init.body).input }, receipt: { sig: "r" } }) : json(404, {}));
  const app = createApp({ publicUrl: "https://modelmarket.dev", fetchImpl, hubUrl: "https://hub.test", hubApiKey: "hk",
                          hearthUrl: "https://hearth.test", hearthApiKey: "k", now: () => Date.parse("2026-11-26T12:00:00Z") });
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  /** One 2026-07-28 request; `headers` overrides headers, a null value drops one; `meta: null` sends no _meta. */
  const modern = async (profile, method, params = {}, { headers = {}, meta = META, id = 1, nameHeader = true } = {}) => {
    const bodyParams = { ...params, ...(meta === null ? {} : { _meta: meta }) };
    const sent = { "content-type": "application/json", accept: "application/json, text/event-stream",
                   "mcp-protocol-version": V, "mcp-method": method };
    if (nameHeader && method === "tools/call" && typeof bodyParams.name === "string") sent["mcp-name"] = bodyParams.name;
    for (const [k, v] of Object.entries(headers)) { if (v === null) delete sent[k.toLowerCase()]; else sent[k.toLowerCase()] = v; }
    const res = await fetch(`${base}/tools/mcp/${profile}`, { method: "POST", headers: sent,
      body: JSON.stringify({ jsonrpc: "2.0", ...(id === null ? {} : { id }), method, params: bodyParams }) });
    return { status: res.status, type: res.headers.get("content-type") || "", session: res.headers.get("mcp-session-id"),
             body: res.status === 202 ? null : await res.json() };
  };
  const legacy = async (profile, method, params, headers = {}) => {
    const res = await fetch(`${base}/tools/mcp/${profile}`, { method: "POST",
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream", ...headers },
      body: JSON.stringify({ jsonrpc: "2.0", id: 7, method, ...(params ? { params } : {}) }) });
    return { status: res.status, session: res.headers.get("mcp-session-id"), body: await res.json() };
  };
  return { modern, legacy, close: () => new Promise((r) => server.close(r)) };
}

const refused = (r, status, code) => {
  assert.equal(r.status, status, JSON.stringify(r.body));
  assert.match(r.type, /^application\/json/);
  assert.equal(r.body.error.code, code);
  return r.body.error;
};

test("server/discover answers without a handshake, on every profile", async () => {
  const s = await serve();
  try {
    for (const profile of ["weather", "security", "domains", "symmartys", "emporion"]) {
      const r = await s.modern(profile, "server/discover");
      assert.equal(r.status, 200, profile);
      assert.equal(r.session, null);
      const out = r.body.result;
      assert.deepEqual(out.supportedVersions, EVERY);
      assert.deepEqual(out.capabilities, { tools: {} });
      assert.equal(out.resultType, "complete");
      assert.equal(typeof out.instructions, "string");
      assert.equal(out._meta["io.modelcontextprotocol/serverInfo"].name, `modelmarket-${profile === "emporion" ? "symmartys" : profile}`);
      assert.ok(out.ttlMs > 0);
      assert.equal(out.cacheScope, "public");
    }
  } finally { await s.close(); }
});

test("tools/list is the same list with the cache fields, and the handshake answer is unchanged", async () => {
  const s = await serve();
  try {
    const old = (await s.legacy("security", "tools/list")).body.result;
    const out = (await s.modern("security", "tools/list")).body.result;
    assert.deepEqual(out.tools, old.tools);
    assert.equal(out.resultType, "complete");
    assert.equal(out.cacheScope, "public");
    assert.ok(out.ttlMs >= 0);
    assert.equal(old.resultType, undefined);
    assert.equal(old.ttlMs, undefined);
    for (const [method, key] of [["resources/list", "resources"], ["prompts/list", "prompts"]]) {
      const empty = (await s.modern("security", method)).body.result;
      assert.deepEqual(empty[key], []);
      assert.equal(empty.resultType, "complete");
      assert.ok("ttlMs" in empty);
    }
  } finally { await s.close(); }
});

test("tools/call runs, says complete, and is not cacheable", async () => {
  const s = await serve();
  try {
    const r = await s.modern("weather", "tools/call", { name: "weather_now", arguments: { city: "Oslo" } });
    assert.equal(r.status, 200, JSON.stringify(r.body));
    assert.equal(r.body.result.resultType, "complete");
    assert.ok(Array.isArray(r.body.result.content));
    assert.equal(r.body.result.ttlMs, undefined);
    const unknown = await s.modern("weather", "tools/call", { name: "no_such_tool", arguments: {} });
    assert.equal(unknown.status, 200);
    assert.equal(unknown.body.error.code, -32602);
  } finally { await s.close(); }
});

test("an unsupported version is answered with the versions spoken", async () => {
  const s = await serve();
  try {
    for (const version of ["2027-01-01", "2025-06-18"]) {
      const error = refused(await s.modern("security", "tools/list", {},
        { meta: { ...META, "io.modelcontextprotocol/protocolVersion": version }, headers: { "MCP-Protocol-Version": version } }),
        400, UNSUPPORTED_PROTOCOL_VERSION);
      assert.deepEqual(error.data, { supported: EVERY, requested: version });
    }
  } finally { await s.close(); }
});

test("headers that disagree with the body, or are missing, are a header mismatch", async () => {
  const s = await serve();
  try {
    for (const headers of [{ "MCP-Protocol-Version": null }, { "MCP-Protocol-Version": "2026-07-29" }, { "Mcp-Method": null }, { "Mcp-Method": "tools/call" }]) {
      const error = refused(await s.modern("security", "tools/list", {}, { headers }), 400, HEADER_MISMATCH);
      assert.match(error.message, /^Header mismatch: /);
    }
    // A modern header with no version in the body is a mismatch, not a handshake request.
    refused(await s.modern("security", "tools/list", {}, { meta: null }), 400, HEADER_MISMATCH);
    const call = { name: "weather_now", arguments: { city: "Oslo" } };
    refused(await s.modern("weather", "tools/call", call, { nameHeader: false }), 400, HEADER_MISMATCH);
    refused(await s.modern("weather", "tools/call", call, { headers: { "Mcp-Name": "air_quality_now" } }), 400, HEADER_MISMATCH);
    refused(await s.modern("weather", "tools/call", call, { headers: { "Mcp-Name": "=?base64?***?=" } }), 400, HEADER_MISMATCH);
    const encoded = `=?base64?${Buffer.from("weather_now").toString("base64")}?=`;
    assert.equal((await s.modern("weather", "tools/call", call, { headers: { "Mcp-Name": encoded } })).status, 200);
    const long = refused(await s.modern("security", "tools/list", {}, { headers: { "Mcp-Method": "x".repeat(500) } }), 400, HEADER_MISMATCH);
    assert.ok(long.message.length < 200);
  } finally { await s.close(); }
});

test("capabilities are required; methods outside the revision are not found; notifications are accepted", async () => {
  const s = await serve();
  try {
    const noCaps = Object.fromEntries(Object.entries(META).filter(([k]) => !k.endsWith("clientCapabilities")));
    refused(await s.modern("security", "tools/list", {}, { meta: noCaps }), 400, -32602);
    refused(await s.modern("security", "tools/list", {}, { meta: { ...META, "io.modelcontextprotocol/clientCapabilities": [] } }), 400, -32602);
    for (const method of ["initialize", "ping", "logging/setLevel", "no/such"]) {
      refused(await s.modern("security", method), 404, -32601);
    }
    assert.equal((await s.modern("security", "notifications/cancelled", { requestId: 1 }, { id: null })).status, 202);
  } finally { await s.close(); }
});

test("handshake clients are not disturbed", async () => {
  const s = await serve();
  try {
    const init = await s.legacy("security", "initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "old", version: "1" } });
    assert.equal(init.status, 200);
    assert.equal(init.body.result.protocolVersion, "2025-06-18");
    assert.equal(init.body.result.resultType, undefined);
    const listed = await s.legacy("security", "tools/list", undefined, { "MCP-Protocol-Version": "2025-06-18" });
    assert.equal(listed.body.result.resultType, undefined);
    assert.deepEqual((await s.legacy("security", "ping")).body.result, {});
  } finally { await s.close(); }
});

test("era detection and header decoding follow the specification's examples", () => {
  const none = () => undefined;
  const header = (value) => (name) => (name === "mcp-protocol-version" ? value : undefined);
  assert.equal(isModern({ method: "tools/list", params: { _meta: { "io.modelcontextprotocol/protocolVersion": V } } }, none), true);
  assert.equal(isModern({ method: "server/discover" }, none), true);
  assert.equal(isModern({ method: "tools/list" }, header("2026-07-28")), true);
  assert.equal(isModern({ method: "tools/list" }, header("2030-01-01")), true);
  assert.equal(isModern({ method: "tools/list" }, header("2025-11-25")), false);
  assert.equal(isModern({ method: "initialize", params: { protocolVersion: V } }, none), false);
  assert.equal(isModern({ method: "tools/list", params: { _meta: { progressToken: 1 } } }, none), false);
  assert.equal(decodeHeaderValue("us-west1"), "us-west1");
  assert.equal(decodeHeaderValue("=?base64?SGVsbG8sIOS4lueVjA==?="), "Hello, 世界");
  assert.equal(decodeHeaderValue("=?base64?IHBhZGRlZCA=?="), " padded ");
  assert.equal(decodeHeaderValue("=?base64?PT9iYXNlNjQ/bGl0ZXJhbD89?="), "=?base64?literal?=");
  assert.equal(decodeHeaderValue("=?BASE64?SGk=?="), "=?BASE64?SGk=?=");
  assert.throws(() => decodeHeaderValue("=?base64?not base64?="));
});
