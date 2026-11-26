import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  createPublicClient, fallback, http, isAddressEqual, parseAbi,
} from "../../argus/node_modules/viem/_esm/index.js";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { base } from "../../argus/node_modules/viem/_esm/chains/index.js";
import { x402Client, x402HTTPClient } from "../../argus/node_modules/@x402/core/dist/esm/client/index.mjs";
import { registerExactEvmScheme } from "../../argus/node_modules/@x402/evm/dist/esm/exact/client/index.mjs";
import { BASE_USDC, recoverCmcSettlement } from "../../argus/src/economy/cmc-settlement.ts";

const endpoint = "https://doc.halowerk.com/ocr";
const payee = "0x2880EdfFF13100677Bf97A3CBdF3Bc34771C4E5E";
const payer = "0x097e3F339D0b023605e12A6B81E2d6Cb7571475a";
const amount = 6000n;
const headers = { "Content-Type": "application/json", "X-HALOWERK-QUELLE": "modelmarket" };
const abi = parseAbi([
  "function balanceOf(address) view returns (uint256)",
  "function authorizationState(address,bytes32) view returns (bool)",
]);
const chain = createPublicClient({
  chain: base,
  transport: fallback([
    http("https://mainnet.base.org", { timeout: 4500, retryCount: 0 }),
    http("https://base-rpc.publicnode.com", { timeout: 4500, retryCount: 0 }),
    http("https://base.drpc.org", { timeout: 4500, retryCount: 0 }),
  ], { retryCount: 0 }),
});
const file = (name: string) => new URL(name, import.meta.url);
const save = (name: string, data: unknown) => writeFile(file(name), JSON.stringify(data, null, 2) + "\n", {
  flag: "wx", mode: 0o600,
});
const rpcBalance = () => chain.readContract({
  address: BASE_USDC, abi, functionName: "balanceOf", args: [payer],
});
const stage = process.argv[2];
assert.ok(stage === "--preflight" || stage === "--pay-once", "Choose preflight or one payment");

const fixture = await readFile(file("sample.pdf"));
const digest = createHash("sha256").update(fixture).digest("hex");
const { payment_required: quote, http_date: date } = JSON.parse(await readFile(file("quote.json"), "utf8"));
assert.equal(quote.x402Version, 2);
assert.equal(quote.resource.url, endpoint);
assert.ok(quote.resource.description.length > 0);
assert.equal(quote.quote.file_sha256, digest);
assert.equal(quote.quote.media_type, "application/pdf");
assert.equal(quote.quote.pages_total, 1);
assert.deepEqual(quote.quote.pages_priced, [1]);
assert.equal(quote.quote.total_usdc, "0.006000");
assert.equal(quote.accepts.length, 1);
const offer = quote.accepts[0];
assert.equal(offer.scheme, "exact");
assert.equal(offer.network, "eip155:8453");
assert.equal(offer.amount, String(amount));
assert.ok(isAddressEqual(offer.asset, BASE_USDC) && isAddressEqual(offer.payTo, payee));
assert.equal(offer.extra.assetTransferMethod, "eip3009");
assert.equal(offer.extra.name, "USD Coin");
assert.equal(offer.extra.version, "2");
assert.equal(offer.extra.eip712Domain.chainId, 8453);
assert.ok(isAddressEqual(offer.extra.eip712Domain.verifyingContract, BASE_USDC));
assert.ok(Number.isInteger(offer.maxTimeoutSeconds) && offer.maxTimeoutSeconds > 0 && offer.maxTimeoutSeconds <= 300);
assert.equal(await chain.getChainId(), 8453);
const before = await rpcBalance();
const block = await chain.getBlock();
assert.ok(Math.abs(Date.now() / 1000 - Number(block.timestamp)) < 45, "Local and Base clocks differ");
console.log(JSON.stringify({ stage, balance_atomic_before: String(before), amount_atomic: String(amount), ready: before >= amount }));
if (stage === "--preflight") process.exit(before >= amount ? 0 : 1);
assert.ok(before >= amount, "Test wallet needs 0.006 Base USDC");
assert.ok(Math.abs(Date.now() - Date.parse(date)) < 240_000, "Get a fresh quote for the exact same PDF");

const walletPath = join(homedir(), ".aicom-pov-buyer.json");
assert.equal((await stat(walletPath)).mode & 0o077, 0);
const wallet = JSON.parse(await readFile(walletPath, "utf8"));
const key = wallet.private_key.startsWith("0x") ? wallet.private_key : `0x${wallet.private_key}`;
delete wallet.private_key;
const signer = privateKeyToAccount(key);
assert.ok(isAddressEqual(signer.address, payer));
const client = new x402Client().setSpendControls({ maxAmountPerPayment: 0.006 });
registerExactEvmScheme(client, { signer, networks: ["eip155:8453"] });
const paymentClient = new x402HTTPClient(client);
const signed = await paymentClient.createPaymentPayload(quote);
assert.deepEqual(signed.accepted, offer);
const authorization = signed.payload.authorization as {
  from: `0x${string}`; to: `0x${string}`; nonce: `0x${string}`; value: string; validBefore: string;
};
assert.ok(isAddressEqual(authorization.from, payer) && isAddressEqual(authorization.to, payee));
assert.equal(authorization.value, String(amount));
assert.match(authorization.nonce, /^0x[0-9a-f]{64}$/i);
assert.ok(Number(authorization.validBefore) * 1000 > Date.now());
const paymentHeaders = paymentClient.encodePaymentSignatureHeader(signed);
assert.deepEqual(Object.keys(paymentHeaders).map((key) => key.toLowerCase()), ["payment-signature"]);

// Exclusive journal creation prevents a second paid request for this test, even after a timeout.
await save("attempt.json", {
  endpoint, payer, payee, amount_atomic: String(amount), attribution: headers["X-HALOWERK-QUELLE"],
  fixture_sha256: digest, nonce: authorization.nonce, valid_before: authorization.validBefore,
  attempted_at: new Date().toISOString(),
});
let response: Response | undefined;
let resultBody: Record<string, any> = {};
let paymentReceipt: Record<string, unknown> = {};
let requestError: string | undefined;
try {
  response = await fetch(endpoint, {
    method: "POST",
    headers: { ...headers, ...paymentHeaders },
    body: JSON.stringify({ image_base64: fixture.toString("base64"), mime: "application/pdf" }),
    redirect: "error",
    signal: AbortSignal.timeout(55_000),
  });
  const receiptHeader = response.headers.get("payment-response");
  if (receiptHeader) paymentReceipt = JSON.parse(Buffer.from(receiptHeader, "base64").toString("utf8"));
  resultBody = await response.json();
} catch (error) {
  // Do not store errors that might include a payment header or raw request.
  requestError = error instanceof Error ? error.name : "UnknownError";
}
const txHint = typeof paymentReceipt.transaction === "string" && /^0x[0-9a-f]{64}$/i.test(paymentReceipt.transaction)
  ? paymentReceipt.transaction as `0x${string}`
  : undefined;
const verification = await Promise.allSettled([
  recoverCmcSettlement(chain, { ...authorization, value: amount }, txHint),
  chain.readContract({ address: BASE_USDC, abi, functionName: "authorizationState", args: [payer, authorization.nonce] }),
  rpcBalance(),
]);
const [settlement, used, after] = verification.map((outcome) => outcome.status === "fulfilled" ? outcome.value : null);
const ocrText = typeof resultBody.text === "string" ? resultBody.text : "";
const expected = [
  "MODEL MARKET OCR TEST", "Synthetic document for the HALOWERK pilot.",
  "Reference: MM-TEST-2046", "Sample code: A0B7", "Control total: 123.45 EUR",
];
const normalizedText = ocrText.replace(/\s+/g, " ").trim();
const matches = Object.fromEntries(expected.map((snippet) => [snippet, normalizedText.includes(snippet)]));
const summary = {
  http_status: response?.status ?? null,
  request_error: requestError,
  attribution_header_sent: headers["X-HALOWERK-QUELLE"],
  provider_request_id: response?.headers.get("x-request-id") ?? null,
  receipt_success: paymentReceipt.success === true,
  receipt_transaction: txHint,
  chain_transaction: settlement,
  authorization_used: used,
  balance_atomic_before: String(before),
  balance_atomic_after: after === null ? null : String(after),
  document_matches: resultBody.document?.sha256 === digest,
  pages_processed: resultBody.document?.pages_processed ?? [],
  engine: resultBody.ocr?.engine,
  ocr_text: ocrText,
  matches,
  block_confidence: Array.isArray(resultBody.blocks) ? resultBody.blocks.map((block) => block.confidence) : [],
  provider_error: typeof resultBody.error === "string" ? resultBody.error.slice(0, 250) : undefined,
};
await save("result.json", summary);
console.log(JSON.stringify(summary, null, 2));
if (!(response?.ok && paymentReceipt.success === true && settlement && summary.document_matches &&
  summary.pages_processed.length === 1 && Object.values(matches).every(Boolean))) process.exitCode = 1;
