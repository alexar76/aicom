// Smoke the tools service image in both MCP eras: no network, the app on a local port with stub upstreams.
import { createApp } from "/app/src/app.js";

const V = "2026-07-28";
const META = { "io.modelcontextprotocol/protocolVersion": V,
               "io.modelcontextprotocol/clientInfo": { name: "smoke", version: "1" },
               "io.modelcontextprotocol/clientCapabilities": {} };
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const fetchImpl = async () => json(404, {});
const app = createApp({ publicUrl: "https://modelmarket.dev", fetchImpl, hubUrl: "https://hub.test", hubApiKey: "hk",
                        hearthUrl: "https://hearth.test", hearthApiKey: "k" });
const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
const base = `http://127.0.0.1:${server.address().port}`;
const must = (ok, what) => { if (!ok) throw new Error(`smoke failed: ${what}`); };
const post = async (profile, method, params, headers) => {
  const res = await fetch(`${base}/tools/mcp/${profile}`, { method: "POST",
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream", ...headers },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) });
  return { status: res.status, session: res.headers.get("mcp-session-id"), body: await res.json() };
};
const modern = (profile, method, params = {}, headers = {}) =>
  post(profile, method, { ...params, _meta: META }, { "mcp-protocol-version": V, "mcp-method": method, ...headers });
const report = {};
try {
  for (const profile of ["weather", "security", "domains", "symmartys"]) {
    const found = await modern(profile, "server/discover");
    must(found.status === 200 && found.session === null, `${profile} discover ${found.status}`);
    must(found.body.result.supportedVersions[0] === V && found.body.result.resultType === "complete", `${profile} discover body`);
    const init = await post(profile, "initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "smoke", version: "1" } }, {});
    must(init.status === 200 && init.body.result.protocolVersion === "2025-06-18" && init.body.result.resultType === undefined, `${profile} initialize`);
    const oldList = (await post(profile, "tools/list", {}, { "mcp-protocol-version": "2025-06-18" })).body.result;
    const newList = (await modern(profile, "tools/list")).body.result;
    must(JSON.stringify(oldList.tools) === JSON.stringify(newList.tools) && newList.resultType === "complete" && oldList.resultType === undefined, `${profile} tools/list`);
    report[profile] = { tools: newList.tools.length, server: found.body.result._meta["io.modelcontextprotocol/serverInfo"] };
  }
  const bad = await modern("security", "tools/list", {}, { "mcp-protocol-version": "2026-07-29" });
  must(bad.status === 400 && bad.body.error.code === -32020, "header mismatch");
  const gone = await modern("security", "initialize");
  must(gone.status === 404 && gone.body.error.code === -32601, "initialize in a modern envelope");
  const docs = await fetch(`${base}/tools/mcp`);
  must(docs.status === 200, `docs page ${docs.status}`);
  report.supportedVersions = (await modern("security", "server/discover")).body.result.supportedVersions;
  console.log(JSON.stringify(report));
} finally { server.close(); }
process.exit(0);
