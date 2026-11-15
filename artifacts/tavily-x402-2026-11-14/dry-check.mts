import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { createPublicClient, fallback, hashDomain, http, isAddressEqual, parseAbi, recoverTypedDataAddress } from "../../argus/node_modules/viem/_esm/index.js";
import { generatePrivateKey, privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { base } from "../../argus/node_modules/viem/_esm/chains/index.js";
import { externalTavilyPayment } from "../../argus/src/economy/external-payment.ts";
import { BASE_USDC } from "../../argus/src/economy/cmc-settlement.ts";

const endpoint = "https://x402.tavily.com/search";
const body = { query: "IETF RFC 9110 status code 402 Payment Required", search_depth: "advanced", max_results: 2 };
const abi = parseAbi(["function DOMAIN_SEPARATOR() view returns (bytes32)", "function balanceOf(address) view returns (uint256)"]);
const rpcs = ["https://mainnet.base.org", "https://base-rpc.publicnode.com", "https://base.drpc.org"];
const rpc = createPublicClient({ chain: base, transport: fallback(rpcs.map(url => http(url, { timeout: 4500, retryCount: 0 })), { retryCount: 0 }) });
const pilot = "0x097e3F339D0b023605e12A6B81E2d6Cb7571475a";
const spot = generatePrivateKey();
const account = privateKeyToAccount(spot);
const [chainId, head, contractDomain, pilotBalance, temporaryBalance] = await Promise.all([
  rpc.getChainId(), rpc.getBlock(), rpc.readContract({ address: BASE_USDC, abi, functionName: "DOMAIN_SEPARATOR" }),
  rpc.readContract({ address: BASE_USDC, abi, functionName: "balanceOf", args: [pilot] }),
  rpc.readContract({ address: BASE_USDC, abi, functionName: "balanceOf", args: [account.address] }),
]);
assert.equal(chainId, 8453);
assert.equal(temporaryBalance, 0n);
const decode = (header) => JSON.parse(Buffer.from(header, "base64").toString("utf8"));
const domain = { name: "USD Coin", version: "2", chainId, verifyingContract: BASE_USDC };
const types = {
  EIP712Domain: [
    { name: "name", type: "string" }, { name: "version", type: "string" },
    { name: "chainId", type: "uint256" }, { name: "verifyingContract", type: "address" },
  ],
  TransferWithAuthorization: [
    { name: "from", type: "address" }, { name: "to", type: "address" }, { name: "value", type: "uint256" },
    { name: "validAfter", type: "uint256" }, { name: "validBefore", type: "uint256" }, { name: "nonce", type: "bytes32" },
  ],
};
assert.equal(hashDomain({ domain, types }), contractDomain);
const quoteHeaders = [];
let requirement;
let signedCheck;
let signedRequestsSent = 0;
const unsigned = await fetch(endpoint, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), redirect: "error", signal: AbortSignal.timeout(12000) });
assert.equal(unsigned.status, 402);
const initialQuote = decode(unsigned.headers.get("payment-required"));
const serverMs = Date.parse(unsigned.headers.get("date"));
assert.ok(Math.abs(serverMs / 1000 - Number(head.timestamp)) < 30, "Tavily and Base clocks differ");
await unsigned.body?.cancel();
const hostOffsetSeconds = Math.round((Date.now() - serverMs) / 1_000);
const originalNow = Date.now;
const started = performance.now();
Date.now = () => Math.floor(serverMs + performance.now() - started);
const pay = externalTavilyPayment(() => spot, async (url, init) => {
  assert.equal(String(url), endpoint);
  assert.equal(init.method, "POST");
  assert.equal(init.redirect, "error");
  assert.deepEqual(JSON.parse(init.body), body);
  const h = new Headers(init.headers);
  const signed = h.get("payment-signature");
  if (!signed) {
    const response = await fetch(url, init);
    assert.equal(response.status, 402);
    requirement = decode(response.headers.get("payment-required"));
    quoteHeaders.push(...response.headers.keys());
    return response;
  }
  const payment = decode(signed);
  const offer = requirement.accepts.find(candidate => candidate.network === "eip155:8453");
  const { authorization, signature } = payment.payload;
  assert.equal(payment.x402Version, 2);
  assert.deepEqual(payment.accepted, offer);
  assert.equal(payment.resource.url, endpoint);
  assert.ok(isAddressEqual(offer.asset, BASE_USDC));
  assert.ok(isAddressEqual(authorization.to, offer.payTo));
  assert.ok(isAddressEqual(authorization.from, account.address));
  assert.equal(authorization.value, "10000");
  assert.match(authorization.nonce, /^0x[0-9a-f]{64}$/);
  assert.ok(Number(authorization.validAfter) < Date.now() / 1000);
  const remainingSeconds = Number(authorization.validBefore) - Math.floor(Date.now() / 1000);
  assert.ok(remainingSeconds > 0 && remainingSeconds <= offer.maxTimeoutSeconds);
  const signer = await recoverTypedDataAddress({
    domain, types, primaryType: "TransferWithAuthorization",
    message: { ...authorization, value: BigInt(authorization.value), validAfter: BigInt(authorization.validAfter), validBefore: BigInt(authorization.validBefore) },
    signature,
  });
  assert.ok(isAddressEqual(signer, account.address));
  signedCheck = { version: payment.x402Version, remaining_seconds: remainingSeconds, recovered_signer_matches: true,
    quote_selection_matches: true, contract_domain_matches: true, payload_extensions: Object.keys(payment.extensions ?? {}) };
  // Stop at the transport boundary. Never send the signed request to Tavily or to an RPC.
  return new Response(null, { status: 402 });
});
try {
  await assert.rejects(pay({ url: endpoint, maxUsd: 0.01, exactUsd: 0.01, body }), /unconfirmed after authorization/);
} finally {
  Date.now = originalNow;
}
assert.ok(signedCheck);
const baseOffer = (quote) => quote.accepts.find(candidate => candidate.network === "eip155:8453");
const result = {
  checked_at: new Date(serverMs).toISOString(), endpoint, chain_id: chainId,
  base_head: String(head.number), base_head_utc: new Date(Number(head.timestamp) * 1000).toISOString(), host_offset_seconds: hostOffsetSeconds,
  offer: { scheme: baseOffer(requirement).scheme, amount_atomic: baseOffer(requirement).amount, asset: BASE_USDC,
    ttl_seconds: baseOffer(requirement).maxTimeoutSeconds, resource: requirement.resource.url },
  same_request_new_recipient: !isAddressEqual(baseOffer(initialQuote).payTo, baseOffer(requirement).payTo),
  networks: requirement.accepts.map(candidate => candidate.network), quote_extensions: Object.keys(requirement.extensions ?? {}),
  challenge_sets_cookie: quoteHeaders.includes("set-cookie"), signed: signedCheck, signed_requests_sent_to_provider: signedRequestsSent,
  pilot_balance_atomic: String(pilotBalance),
};
const target = new URL("./dry-check.json", import.meta.url);
await writeFile(target, JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
