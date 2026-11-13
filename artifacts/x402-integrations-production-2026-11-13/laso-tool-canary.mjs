import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { performance } from "node:perf_hooks";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { buildLasoCardTools } from "../../argus/dist/tools/laso.js";
import { lasoWalletAuth } from "../../argus/dist/tools/laso-auth.js";

const keyPath = join(homedir(), ".aicom-pov-buyer.json");
if (statSync(keyPath).mode & 0o077) throw new Error("Expected an owner-only buyer key file");
const saved = JSON.parse(readFileSync(keyPath, "utf8"));
const key = saved.private_key.startsWith("0x") ? saved.private_key : `0x${saved.private_key}`;
delete saved.private_key;
const payer = privateKeyToAccount(key).address.toLowerCase();
if (payer !== "0x097e3f339d0b023605e12a6b81e2d6cb7571475a") throw new Error("Unexpected buyer");
const time = await fetch("https://api.coinbase.com/v2/time", { signal: AbortSignal.timeout(10000) });
const clock = await time.json();
const date = Date.parse(time.headers.get("date"));
if (!time.ok || !Number.isFinite(date) || Math.abs(date / 1000 - clock.data?.epoch) > 2) throw new Error("Time source disagreed");
const tick = performance.now();
Date.now = () => Math.floor(date + performance.now() - tick);

const requests = [];
async function observe(input, init) {
  const url = new URL(input);
  if (url.origin !== "https://laso.finance" || !["/auth", "/search-merchants"].includes(url.pathname)) {
    throw new Error("Unexpected Laso request");
  }
  const response = await fetch(input, init);
  requests.push({ path: url.pathname, status: response.status });
  return response;
}
const session = lasoWalletAuth(() => key, observe);
const first = await session();
if (first !== await session() || requests.length !== 2) throw new Error("Laso session did not reuse its token");

const results = [];
for (const merchant of ["Uber", "Amazon"]) {
  const [quote, issue] = buildLasoCardTools({ merchant, maxCents: 500, token: () => first, fetch: observe,
    pay: () => { throw new Error("This canary allows no paid path"); }, hasOwnerChannel: () => false });
  const response = await quote.run({ checkoutCents: 500 }, { approved: false });
  const denied = await issue.run({}, { approved: false });
  results.push({ merchant, quote_accepted: response.ok, payment_without_approval_denied: !denied.ok });
}
console.log(JSON.stringify({ payer, requests, token_cache_verified: true, paid: false, results }, null, 2));
if (results[0].quote_accepted || !results[1].quote_accepted || results.some((r) => !r.payment_without_approval_denied)) process.exitCode = 1;
