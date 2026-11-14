import { lstatSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { performance } from "node:perf_hooks";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { lasoWalletAuth } from "../../argus/dist/tools/laso-auth.js";

// The token goes directly to the private file installer on Attested via a pipe.
const request = () => ({ redirect: "error", signal: AbortSignal.timeout(12_000) });
const [clock, chain] = await Promise.all([
  fetch("https://api.coinbase.com/v2/time", request()),
  fetch("https://base-rpc.publicnode.com", {
    ...request(), method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getBlockByNumber", params: ["latest", false] }),
  }),
]);
const epoch = (await clock.json()).data.epoch;
const blockTime = Number((await chain.json()).result.timestamp);
const httpsTime = Date.parse(clock.headers.get("date") ?? "");
if (!clock.ok || !chain.ok || !Number.isFinite(httpsTime) || !Number.isFinite(blockTime)
  || Math.abs(httpsTime / 1000 - epoch) > 2 || Math.abs(httpsTime / 1000 - blockTime) > 30) {
  throw new Error("Could not verify Laso sign-in time");
}
const tick = performance.now();
Date.now = () => Math.floor(httpsTime + performance.now() - tick);

const file = join(homedir(), ".aicom-pov-buyer.json");
const stat = lstatSync(file);
if (!stat.isFile() || stat.uid !== process.getuid() || (stat.mode & 0o077)) throw new Error("Expected private checkout key file");
const { private_key: raw } = JSON.parse(readFileSync(file, "utf8"));
const key = raw.startsWith("0x") ? raw : `0x${raw}`;
if (privateKeyToAccount(key).address.toLowerCase() !== "0x097e3f339d0b023605e12a6b81e2d6cb7571475a") throw new Error("Unexpected checkout wallet");
const token = await lasoWalletAuth(() => key)();
const installer = readFileSync(new URL("./install-existing-laso-session.mjs", import.meta.url), "utf8");
const shellQuote = value => "'" + value.replace(/'/g, "'\\''") + "'";
const install = spawn("ssh", ["-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "attested",
  "docker exec -i argus node --input-type=module -e " + shellQuote(installer)],
{ stdio: ["pipe", "inherit", "inherit"] });
install.stdin.on("error", () => {});
install.stdin.end(token);
const [code] = await once(install, "exit");
if (code !== 0) throw new Error("Laso session install was not confirmed");
