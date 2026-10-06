// The buying step against a local fake seller that checks the EIP-712 signature for real (throwaway key, no
// network, no chain): what gets signed, when nothing is signed, and how the answer is recorded.
import assert from "node:assert/strict";
import { test } from "node:test";
import { getAddress, verifyTypedData } from "viem";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { USDC_BASE, buyOne, chargedOnChain, checkPayload, payingClient, terms } from "../lib.mjs";

const CAP = 10_000n;
const SELLER = "0x00000000000000000000000000000000000000a1";
const account = privateKeyToAccount(generatePrivateKey());
const http = payingClient(account, "$0.01");

const offer = (over = {}) => ({
  scheme: "exact", network: "eip155:8453", asset: getAddress(USDC_BASE), amount: "5000", payTo: SELLER,
  maxTimeoutSeconds: 300, extra: { name: "USD Coin", version: "2" }, ...over,
});
const entry = (over = {}) => ({
  host: "seller.example.com", resource: "https://seller.example.com/quote",
  input: { method: "POST", bodyType: "json", body: { symbol: "ETH" } }, listed: terms(offer()), ...over,
});
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64");
const required = (accepts) => ({ "payment-required": b64({ x402Version: 2, resource: { url: "https://seller.example.com/quote" }, accepts }) });

const TYPES = { TransferWithAuthorization: [
  { name: "from", type: "address" }, { name: "to", type: "address" }, { name: "value", type: "uint256" },
  { name: "validAfter", type: "uint256" }, { name: "validBefore", type: "uint256" }, { name: "nonce", type: "bytes32" }] };

/** A seller that quotes `quoted`, accepts only a valid signature for Base USDC, then answers `answer`. */
function fakeSeller({ quoted = offer(), answer = { status: 200, body: '{"price":3120.5}' } } = {}) {
  const calls = [];
  const send = async (req) => {
    calls.push(req);
    const sig = req.headers["PAYMENT-SIGNATURE"];
    if (!sig) return { status: 402, headers: required([quoted]), body: Buffer.from("{}"), ms: 5 };
    const payload = JSON.parse(Buffer.from(sig, "base64").toString("utf8"));
    const a = payload.payload.authorization;
    const valid = await verifyTypedData({
      address: a.from, signature: payload.payload.signature, types: TYPES, primaryType: "TransferWithAuthorization",
      domain: { name: "USD Coin", version: "2", chainId: 8453, verifyingContract: getAddress(USDC_BASE) },
      message: { from: a.from, to: a.to, value: BigInt(a.value), validAfter: BigInt(a.validAfter), validBefore: BigInt(a.validBefore), nonce: a.nonce },
    });
    if (!valid) return { status: 402, headers: required([quoted]), body: Buffer.from('{"error":"invalid_signature"}'), ms: 5 };
    if (answer.status === 402) return { status: 402, headers: required([quoted]), body: Buffer.from('{"error":"insufficient_funds"}'), ms: 5 };
    const settled = b64({ success: true, transaction: `0x${"ab".repeat(32)}`, network: "eip155:8453", payer: a.from });
    return { status: answer.status, headers: { "content-type": "application/json", "payment-response": settled }, body: Buffer.from(answer.body), ms: 7 };
  };
  return { send, calls };
}

const ctx = (send, budgetLeft = 550_000n) => ({ http, payer: account.address, cap: CAP, budgetLeft, send });

test("pays exactly the approved transfer and keeps the answer as evidence", async () => {
  const seller = fakeSeller();
  const row = await buyOne(entry(), terms(offer()), ctx(seller.send));
  assert.equal(row.verdict, "answered");
  assert.equal(seller.calls.length, 2);
  assert.equal(row.signed.value, "5000");
  assert.equal(row.signed.to, getAddress(SELLER));
  assert.equal(row.signed.from, account.address);
  assert.equal(row.settle.success, true);
  assert.equal(Buffer.from(row.response.body_b64, "base64").toString(), '{"price":3120.5}');
  assert.equal(row.sent.body, '{"symbol":"ETH"}');
  assert.equal(seller.calls[1].body, seller.calls[0].body);
});

test("nothing is signed when the live terms differ from the approved ones", async () => {
  for (const [quoted, verdict] of [
    [offer({ amount: "6000" }), "terms_changed_since_approval"],
    [offer({ payTo: "0x00000000000000000000000000000000000000b2" }), "payee_changed"],
    [offer({ amount: "20000" }), "over_cap"],
    [offer({ extra: { name: "USDC", version: "2" } }), "wrong_usdc_domain"],
    [offer({ extra: { name: "USD Coin", version: "2", assetTransferMethod: "permit2" } }), "not_eip3009"],
  ]) {
    const seller = fakeSeller({ quoted });
    const row = await buyOne(entry(), terms(offer()), ctx(seller.send));
    assert.equal(row.verdict, verdict);
    assert.equal(row.signed, undefined);
    assert.equal(seller.calls.length, 1, verdict);
  }
});

test("the budget stops a payment before it is signed", async () => {
  const seller = fakeSeller();
  const row = await buyOne(entry(), terms(offer()), ctx(seller.send, 4_999n));
  assert.equal(row.verdict, "over_budget");
  assert.equal(seller.calls.length, 1);
});

test("a refused payment and an error after payment are told apart", async () => {
  const refused = await buyOne(entry(), terms(offer()), ctx(fakeSeller({ answer: { status: 402 } }).send));
  assert.equal(refused.verdict, "payment_refused");
  assert.equal(refused.refusal, "insufficient_funds");
  assert.ok(refused.signed);
  const broken = await buyOne(entry(), terms(offer()), ctx(fakeSeller({ answer: { status: 500, body: "oops" } }).send));
  assert.equal(broken.verdict, "error_after_payment");
  const empty = await buyOne(entry(), terms(offer()), ctx(fakeSeller({ answer: { status: 200, body: "" } }).send));
  assert.equal(empty.verdict, "empty_answer");
});

test("no answer after payment is recorded with the authorization that may still settle", async () => {
  let n = 0;
  const seller = fakeSeller();
  const send = async (req, opts) => (n++ === 0 ? seller.send(req, opts) : { error: "timeout", ms: 90_000 });
  const row = await buyOne(entry(), terms(offer()), ctx(send));
  assert.equal(row.verdict, "no_answer_after_payment");
  assert.ok(row.signed.nonce);
});

test("a payload for another payee or amount never leaves the process", () => {
  const approved = terms(offer());
  const good = { payload: { signature: "0x00", authorization: { from: account.address, to: SELLER, value: "5000", validAfter: "0", validBefore: "1900000000", nonce: `0x${"11".repeat(32)}` } } };
  assert.equal(checkPayload(good, { payer: account.address, approved }).value, "5000");
  const bad = (patch) => ({ payload: { ...good.payload, authorization: { ...good.payload.authorization, ...patch } } });
  assert.throws(() => checkPayload(bad({ to: "0x00000000000000000000000000000000000000b2" }), { payer: account.address, approved }));
  assert.throws(() => checkPayload(bad({ value: "50000" }), { payer: account.address, approved }));
  assert.throws(() => checkPayload(bad({ from: SELLER }), { payer: account.address, approved }));
  assert.throws(() => checkPayload({ payload: { signature: "0x00", permit2Authorization: {} } }, { payer: account.address, approved }));
});

test("the reference client's own cap refuses a payment above the survey's", async () => {
  const pricey = offer({ amount: "20000" });
  await assert.rejects(http.createPaymentPayload({ x402Version: 2, resource: { url: "https://seller.example.com/quote" }, accepts: [pricey] }));
});

test("charged is read from USDC's authorizationState, retried, null when unknown", async () => {
  const rows = [
    { host: "a", signed: { from: account.address, nonce: `0x${"01".repeat(32)}`, value: "1000", valid_before: "1" }, settle: { transaction: "0xabc" } },
    { host: "b", signed: { from: account.address, nonce: `0x${"02".repeat(32)}`, value: "2000", valid_before: "1" } },
    { host: "c" },
  ];
  const seen = [];
  const read = async ({ args, functionName }) => { seen.push(functionName); if (args[1].endsWith("01")) return true; throw new Error("rpc down"); };
  const out = await chargedOnChain(rows, read, { backoffMs: 10 });
  assert.deepEqual(out.map((r) => [r.host, r.charged]), [["a", true], ["b", null]]);
  assert.equal(out[0].claimed_tx, "0xabc");
  assert.ok(seen.every((f) => f === "authorizationState"));
});

test("each drawn seller ends in one outcome, from the furthest stage it reached", async () => {
  const { outcome } = await import("../lib.mjs");
  const signed = { value: "5000" };
  assert.deepEqual(outcome({ verdict: "timeout" }, undefined, undefined, undefined), { outcome: "not_bought", why: "timeout" });
  assert.equal(outcome({}, { verdict: "terms_changed_since_approval" }, undefined, undefined).outcome, "not_bought");
  assert.equal(outcome({}, { signed, verdict: "error_after_payment" }, { charged: true }, undefined).outcome, "charged_no_answer");
  assert.equal(outcome({}, { signed, verdict: "payment_refused" }, { charged: false }, undefined).outcome, "not_charged_no_answer");
  assert.equal(outcome({}, { signed, verdict: "no_answer_after_payment" }, { charged: null }, undefined).outcome, "charge_unknown_no_answer");
  const answered = { signed, verdict: "answered", response: { content_type: "application/json" } };
  assert.equal(outcome({}, answered, { charged: true }, { kind: "verdict", genuine: true, passed: true, score: 0.9, reasons: ["ok"] }).outcome, "delivered");
  const failed = outcome({}, answered, { charged: true }, { kind: "verdict", genuine: true, passed: false, score: 0.2, reasons: ["placeholder"] });
  assert.deepEqual([failed.outcome, failed.why, failed.score], ["failed_the_order", "placeholder", 0.2]);
  assert.equal(outcome({}, answered, { charged: true }, { kind: "verdict", genuine: false, cause: "audit_untrusted" }).why, "audit_untrusted");
  assert.equal(outcome({}, { ...answered, response: { content_type: "image/png" } }, { charged: true }, undefined).why, "binary");
});
