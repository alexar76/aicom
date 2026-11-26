import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { createPublicClient, fallback, http, isAddressEqual, parseAbi } from "../../argus/node_modules/viem/_esm/index.js";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { base } from "../../argus/node_modules/viem/_esm/chains/index.js";
import { x402Client, x402HTTPClient } from "../../argus/node_modules/@x402/core/dist/esm/client/index.mjs";
import { registerExactEvmScheme } from "../../argus/node_modules/@x402/evm/dist/esm/exact/client/index.mjs";
import { BASE_USDC, recoverCmcSettlement } from "../../argus/src/economy/cmc-settlement.ts";

const hub = "http://127.0.0.1:19183";
const provider = "https://doc.halowerk.com/ocr";
const payee = "0x2880EdfFF13100677Bf97A3CBdF3Bc34771C4E5E";
const payer = "0x097e3F339D0b023605e12A6B81E2d6Cb7571475a";
const amount = 6000n;
const file = (name: string) => new URL(name, import.meta.url);
const save = (name: string, data: unknown) => writeFile(file(name), JSON.stringify(data, null, 2) + "\n", {
  flag: "wx", mode: 0o600,
});
const decode = (value: string | null) => value ? JSON.parse(Buffer.from(value, "base64").toString("utf8")) : {};
const stage = process.argv[2];
assert.ok(stage === "--quote-only" || stage === "--pay-once");

const search = await fetch(hub + "/ai-market/v2/search?intent=HALOWERK+OCR&budget=0.006", {
  redirect: "error", signal: AbortSignal.timeout(15_000),
});
assert.equal(search.status, 200);
const card = (await search.json()).external.find((row) => row.id === "halowerk-ocr");
assert.ok(card);
assert.equal(card.endpoint, "/ai-market/v2/external-services/halowerk-ocr/ocr");
assert.equal(card.provider_endpoint, provider);
assert.equal(card.payment_recipient, "provider");
assert.equal(card.method, "POST");
const fixture = await readFile(file("sample.pdf"));
const digest = createHash("sha256").update(fixture).digest("hex");
const body = JSON.stringify({ image_base64: fixture.toString("base64"), mime: "application/pdf" });
const post = (additionalHeaders?: Record<string, string>) => fetch(hub + card.endpoint, {
  method: "POST",
  headers: { "Content-Type": "application/json", ...additionalHeaders },
  body, redirect: "error", signal: AbortSignal.timeout(45_000),
});
const quoted = await post();
assert.equal(quoted.status, 402, `Unexpected quote response: ${quoted.status} ${(await quoted.text()).slice(0, 500)}`);
const quote = decode(quoted.headers.get("payment-required"));
assert.equal(quote.x402Version, 2);
assert.equal(quote.resource.url, provider);
assert.equal(quote.resource.description, card.description);
assert.equal(quote.quote.file_sha256, digest);
assert.equal(quote.quote.pages_total, 1);
assert.equal(quote.quote.total_usdc, "0.006000");
assert.equal(quote.accepts.length, 1);
const offer = quote.accepts[0];
assert.equal(offer.network, "eip155:8453");
assert.equal(offer.scheme, "exact");
assert.equal(offer.amount, String(amount));
assert.ok(isAddressEqual(offer.asset, BASE_USDC) && isAddressEqual(offer.payTo, payee));
assert.equal(offer.extra.assetTransferMethod, "eip3009");
assert.equal(offer.extra.eip712Domain.chainId, 8453);
assert.ok(isAddressEqual(offer.extra.eip712Domain.verifyingContract, BASE_USDC));
const quoteSummary = { card, http_status: quoted.status, exact_amount_atomic: offer.amount, fixture_sha256: digest };
console.log(JSON.stringify(quoteSummary));
if (stage === "--quote-only") {
  await save("modelmarket-quote.json", quoteSummary);
  process.exit(0);
}

const chain = createPublicClient({
  chain: base,
  transport: fallback([
    http("https://mainnet.base.org", { timeout: 4500, retryCount: 0 }),
    http("https://base-rpc.publicnode.com", { timeout: 4500, retryCount: 0 }),
    http("https://base.drpc.org", { timeout: 4500, retryCount: 0 }),
  ], { retryCount: 0 }),
});
const balance = () => chain.readContract({
  address: BASE_USDC, abi: parseAbi(["function balanceOf(address) view returns (uint256)"]),
  functionName: "balanceOf", args: [payer],
});
assert.equal(await chain.getChainId(), 8453);
assert.ok(Math.abs(Date.now() / 1000 - Number((await chain.getBlock()).timestamp)) < 45);
const before = await balance();
assert.ok(before >= amount, "Test wallet needs 0.006 Base USDC");
const keyPath = join(homedir(), ".aicom-pov-buyer.json");
assert.equal((await stat(keyPath)).mode & 0o077, 0);
const { private_key } = JSON.parse(await readFile(keyPath, "utf8"));
const signer = privateKeyToAccount(private_key.startsWith("0x") ? private_key : `0x${private_key}`);
assert.ok(isAddressEqual(signer.address, payer));
const client = new x402Client().setSpendControls({ maxAmountPerPayment: 0.006 });
registerExactEvmScheme(client, { signer, networks: ["eip155:8453"] });
const x402 = new x402HTTPClient(client);
const signed = await x402.createPaymentPayload(quote);
assert.deepEqual(signed.accepted, offer);
const authorization = signed.payload.authorization as {
  from: `0x${string}`; to: `0x${string}`; nonce: `0x${string}`; value: string; validBefore: string;
};
assert.ok(isAddressEqual(authorization.from, payer) && isAddressEqual(authorization.to, payee));
assert.equal(authorization.value, String(amount));
assert.ok(Number(authorization.validBefore) * 1000 > Date.now());
const paymentHeaders = x402.encodePaymentSignatureHeader(signed);
assert.deepEqual(Object.keys(paymentHeaders).map((key) => key.toLowerCase()), ["payment-signature"]);
await save("modelmarket-attempt.json", {
  endpoint: hub + card.endpoint, payer, payee, nonce: authorization.nonce,
  amount_atomic: String(amount), valid_before: authorization.validBefore, attempted_at: new Date().toISOString(),
});

let response: Response | undefined;
let payment = {};
let result = {};
let failure: string | undefined;
try {
  response = await post(paymentHeaders);
  payment = decode(response.headers.get("payment-response"));
  result = await response.json();
} catch (error) {
  failure = error instanceof Error ? error.name : "UnknownError";
}
const tx = payment.transaction;
const hint = typeof tx === "string" && /^0x[0-9a-f]{64}$/i.test(tx) ? tx as `0x${string}` : undefined;
const checks = await Promise.allSettled([
  recoverCmcSettlement(chain, { ...authorization, value: amount }, hint),
  balance(),
]);
const [settled, after] = checks.map((outcome) => outcome.status === "fulfilled" ? outcome.value : null);
const summary = {
  via: hub + card.endpoint,
  http_status: response?.status ?? null,
  failure,
  quote_amount_atomic: offer.amount,
  receipt_success: payment.success === true,
  receipt_network: payment.network,
  provider_request_id: response?.headers.get("x-request-id"),
  tracked: response?.headers.get("x-modelmarket-tracked") === "true",
  transaction: settled,
  receipt_transaction: hint,
  balance_atomic_before: String(before),
  balance_atomic_after: after === null ? null : String(after),
  document_matches: result.document?.sha256 === digest,
  pages_processed: result.document?.pages_processed,
  ocr_text: result.text,
  block_confidence: result.blocks?.map((block) => block.confidence),
  provider_error: typeof result.detail === "string" ? result.detail : undefined,
};
await save("modelmarket-result.json", summary);
console.log(JSON.stringify(summary, null, 2));
if (!(response?.ok && payment.success && settled && summary.tracked && summary.document_matches)) process.exitCode = 1;
