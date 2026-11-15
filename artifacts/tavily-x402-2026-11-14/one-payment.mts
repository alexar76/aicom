import assert from "node:assert/strict";
import { readFile, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { createPublicClient, fallback, http, isAddressEqual, parseAbi } from "../../argus/node_modules/viem/_esm/index.js";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { base } from "../../argus/node_modules/viem/_esm/chains/index.js";
import { x402Client } from "../../argus/node_modules/@x402/core/dist/esm/client/index.mjs";
import { registerExactEvmScheme } from "../../argus/node_modules/@x402/evm/dist/esm/exact/client/index.mjs";
import { wrapFetchWithPayment } from "../../argus/node_modules/@x402/fetch/dist/esm/index.mjs";
import { BASE_USDC, recoverCmcSettlement } from "../../argus/src/economy/cmc-settlement.ts";

const endpoint = "https://x402.tavily.com/search";
const payer = "0x097e3F339D0b023605e12A6B81E2d6Cb7571475a";
const amount = 10_000n;
const abi = parseAbi(["function balanceOf(address) view returns (uint256)", "function authorizationState(address,bytes32) view returns (bool)"]);
const rpc = createPublicClient({ chain: base, transport: fallback(["https://mainnet.base.org", "https://base-rpc.publicnode.com", "https://base.drpc.org"].map(url => http(url, { timeout: 4500, retryCount: 0 })), { retryCount: 0 }) });
const balance = () => rpc.readContract({ address: BASE_USDC, abi, functionName: "balanceOf", args: [payer] });
const used = nonce => rpc.readContract({ address: BASE_USDC, abi, functionName: "authorizationState", args: [payer, nonce] });
const save = (name, data) => writeFile(new URL(`./canary-${name}.json`, import.meta.url), JSON.stringify(data, null, 2) + "\n", { flag: "wx", mode: 0o600 });
const [chainId, before, head] = await Promise.all([rpc.getChainId(), balance(), rpc.getBlock()]);
assert.equal(chainId, 8453);
const previous = new URL("../x402-integrations-production-2026-11-13/", import.meta.url);
for (const attempt of ["tavily", "tavily-retry", "tavily-sdk"]) {
  const prior = JSON.parse(await readFile(new URL(`${attempt}-attempt.json`, previous), "utf8"));
  assert.ok(isAddressEqual(prior.payer, payer));
  assert.ok(head.timestamp > BigInt(prior.valid_before) && (await used(prior.authorization_nonce)) === false, "A previous authorization is still active or was used");
}
if (process.argv[2] !== "--one-payment") {
  console.log(JSON.stringify({ balance_atomic: String(before), required_atomic: String(amount), ready: before >= amount, sends_authorization: false }));
  process.exit(0);
}
assert.ok(before >= amount, "Test wallet lacks 0.01 Base USDC");
const path = join(homedir(), ".aicom-pov-buyer.json");
assert.equal((await stat(path)).mode & 0o077, 0);
const wallet = JSON.parse(await readFile(path, "utf8"));
const key = wallet.private_key.startsWith("0x") ? wallet.private_key : `0x${wallet.private_key}`;
delete wallet.private_key;
const signer = privateKeyToAccount(key);
assert.ok(isAddressEqual(signer.address, payer));

const decode = h => h ? JSON.parse(Buffer.from(h, "base64").toString("utf8")) : undefined;
const client = new x402Client().setSpendControls({ maxAmountPerPayment: 0.01 });
registerExactEvmScheme(client, { signer, networks: ["eip155:8453"] });
const originalNow = Date.now;
let authorization, decision, response, delivery;
client.onBeforePaymentCreation(({ paymentRequired, selectedRequirements: offer }) => {
  if (paymentRequired.x402Version !== 2 || paymentRequired.resource?.url !== endpoint || offer.scheme !== "exact"
      || offer.network !== "eip155:8453" || offer.amount !== String(amount) || !isAddressEqual(offer.asset, BASE_USDC)
      || offer.extra?.name !== "USD Coin" || offer.extra?.version !== "2"
      || (offer.extra.assetTransferMethod ?? "eip3009") !== "eip3009" || offer.maxTimeoutSeconds !== 60) {
    return { abort: true, reason: "Unexpected Tavily quote" };
  }
  decision = offer;
});
const observedFetch = async (input, options) => {
  const url = input instanceof Request ? input.url : String(input);
  assert.equal(url, endpoint);
  const signed = decode(new Headers(input instanceof Request ? input.headers : options.headers).get("payment-signature"));
  if (!signed) {
    const quote = await fetch(input, options);
    assert.equal(quote.status, 402);
    const epoch = Date.parse(quote.headers.get("date"));
    const elapsed = performance.now();
    assert.ok(Math.abs(epoch / 1000 - Number(head.timestamp)) < 45, "Tavily and Base clocks differ");
    Date.now = () => Math.floor(epoch + performance.now() - elapsed);
    return quote;
  }
  assert.equal(authorization, undefined, "Payment already attempted");
  const a = signed.payload.authorization;
  assert.deepEqual(signed.accepted, decision);
  assert.ok(isAddressEqual(a.from, payer) && isAddressEqual(a.to, decision.payTo));
  assert.equal(a.value, String(amount));
  assert.match(a.nonce, /^0x[0-9a-f]{64}$/);
  assert.ok(Number(a.validBefore) * 1000 > Date.now());
  // Exclusive creation also prevents duplicate launches from sending a second authorization.
  await save("sent", { endpoint, payer, to: a.to, nonce: a.nonce, amount_atomic: a.value, valid_before: a.validBefore, checked_at: new Date(Date.now()).toISOString() });
  authorization = a;
  return fetch(input, options);
};
try {
  response = await wrapFetchWithPayment(observedFetch, client)(endpoint, {
    method: "POST", redirect: "error", signal: AbortSignal.timeout(90_000), headers: { "content-type": "application/json" },
    body: JSON.stringify({ query: "IETF RFC 9110 status code 402 Payment Required", max_results: 2 }),
  });
  const receipt = decode(response.headers.get("payment-response"));
  const quote = decode(response.headers.get("payment-required"));
  const txHint = receipt?.transaction?.match(/^0x[0-9a-f]{64}$/i)?.[0];
  const transaction = authorization ? await recoverCmcSettlement(rpc, {
    from: payer, to: authorization.to, nonce: authorization.nonce, value: amount,
  }, txHint) : null;
  const status = response.status;
  const result = response.ok ? await response.json() : null;
  const links = Array.isArray(result?.results) ? result.results.map(({ url }) => url).filter(url => typeof url === "string" && /^https?:\/\//.test(url)) : [];
  delivery = { status, provider_error: quote?.error, receipt_success: receipt?.success === true, transaction,
    base_nonce_used_at_check: authorization && await used(authorization.nonce),
    before_atomic: String(before), after_atomic_at_check: String(await balance()), links };
} catch (error) {
  if (!authorization) throw error;
  delivery = { status: response?.status, delivery_unconfirmed: true,
    // Transport errors can contain request/payment material. Do not persist raw errors.
    reconcile_nonce_before_retry: true };
} finally {
  Date.now = originalNow;
}
await save("result", delivery);
console.log(JSON.stringify(delivery, null, 2));
if (!(delivery.status === 200 && delivery.receipt_success && delivery.transaction && delivery.links?.length)) process.exitCode = 1;
