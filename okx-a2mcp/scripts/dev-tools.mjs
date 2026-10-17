// Local preview of the /tools/ pages: node scripts/dev-tools.mjs [port]
//
// The gateway app as in production, with two stand-ins: the hearth is emulated by running the
// real agent handlers from ../hestia-agents in python3 (unsigned: there is no hearth key here),
// and /assets/* — the site's stylesheet and fonts, which the hub serves in production — is
// fetched from modelmarket.dev. histor-check and warden-scan are the real services.
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createApp } from "../src/app.js";

const port = Number(process.argv[2] || 9491);
const HEARTH = "http://hearth.local";
const AGENTS = fileURLToPath(new URL("../../hestia-agents/agents/", import.meta.url));
const DIRS = { "x402.authorization.check@v1": "x402-check", "mcp.tools.diff@v1": "mcp-diff" };
const RUN = "import importlib.util,json,sys\n"
  + "s=importlib.util.spec_from_file_location('h',sys.argv[1]+'/handler.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
  + "try:\n print(json.dumps({'ok':True,'result':m.handle(json.load(sys.stdin))}))\n"
  + "except Exception as e:\n print(json.dumps({'ok':False,'error':str(e)[:300]}))\n";

function runAgent(dir, input) {
  return new Promise((resolve) => {
    const child = execFile("python3", ["-I", "-c", RUN, AGENTS + dir], { timeout: 20_000 }, (err, stdout) => {
      if (err) return resolve({ ok: false, error: String(err.message).slice(0, 300) });
      resolve(JSON.parse(stdout));
    });
    child.stdin.end(JSON.stringify(input));
  });
}

async function fetchImpl(url, init) {
  if (String(url).startsWith(HEARTH)) {
    const { capability_id: cap, input } = JSON.parse(init.body);
    const out = await runAgent(DIRS[cap], input);
    const body = out.ok ? { ...out, provider_pubkey: "local-preview-unsigned", signature: null } : out;
    return new Response(JSON.stringify(body), { status: out.ok ? 200 : 400, headers: { "content-type": "application/json" } });
  }
  return fetch(url, init);
}

const app = createApp({ fetchImpl, hearthUrl: HEARTH, hearthApiKey: "local", publicUrl: `http://localhost:${port}`, trustProxy: false });
// createApp ends with a JSON 404, so the asset relay sits in an outer app in front of it.
const relay = async (req, res) => {
  const upstream = await fetch("https://modelmarket.dev" + req.originalUrl);
  res.status(upstream.status).set("Content-Type", upstream.headers.get("content-type") || "application/octet-stream")
    .send(Buffer.from(await upstream.arrayBuffer()));
};
const server = (await import("express")).default();
server.get("/assets/*rest", relay);
server.use(app);
server.listen(port, "127.0.0.1", () => console.log(`tools preview on http://localhost:${port}/tools/`));
