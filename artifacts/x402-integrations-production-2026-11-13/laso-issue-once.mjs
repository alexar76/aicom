import { existsSync, lstatSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { performance } from "node:perf_hooks";
import { setTimeout as delay } from "node:timers/promises";
import { createPublicClient, fallback, http, parseAbi, parseAbiItem } from "../../argus/node_modules/viem/_esm/index.js";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { base } from "../../argus/node_modules/viem/_esm/chains/index.js";
import { BASE_USDC, recoverCmcSettlement } from "../../argus/dist/economy/cmc-settlement.js";
import { externalBasePayment, readProviderJson } from "../../argus/dist/economy/external-payment.js";
import { lasoWalletAuth } from "../../argus/dist/tools/laso-auth.js";

const origin = "https://laso.finance";
const endpoint = `${origin}/get-card?amount=5.00`;
const payer = "0x097e3f339d0b023605e12a6b81e2d6cb7571475a";
const payee = "0x3291e96b3bff7ed56e3ca8364273c5b4654b2b37";
const amount = 5_000_000n;
const hashPattern = /^0x[\da-f]{64}$/i;
const idPattern = /^[A-Za-z0-9_-]{1,100}$/;
const artifact = (name) => new URL(`./laso-issue-${name}.json`, import.meta.url);
const read = (name) => JSON.parse(readFileSync(artifact(name), "utf8"));
function save(name, value, flag = "wx") {
  writeFileSync(artifact(name), `${JSON.stringify(value, null, 2)}\n`, { flag, mode: 0o600 });
}
const mode = process.argv[2];
if (!["preflight", "sign-check", "issue", "verify"].includes(mode)) throw new Error("Choose preflight, sign-check, issue or verify");
if (mode === "issue" && existsSync(artifact("attempt"))) throw new Error("Payment already attempted. Use verify.");

const keyPath = join(homedir(), ".aicom-pov-buyer.json");
const keyFile = lstatSync(keyPath);
if (!keyFile.isFile() || keyFile.uid !== process.getuid() || keyFile.mode & 0o077) throw new Error("Expected an owner-only buyer key file");
const saved = JSON.parse(readFileSync(keyPath, "utf8"));
const key = saved.private_key.startsWith("0x") ? saved.private_key : `0x${saved.private_key}`;
delete saved.private_key;
if (privateKeyToAccount(key).address.toLowerCase() !== payer) throw new Error("Unexpected test buyer");

const rpcUrls = ["https://base-rpc.publicnode.com", "https://mainnet.base.org", "https://base.drpc.org"];
const chain = createPublicClient({ chain: base, transport: fallback(rpcUrls.map((url) => http(url, { timeout: 5000, retryCount: 0 })), { retryCount: 0 }) });
const abi = parseAbi(["function balanceOf(address) view returns (uint256)"]);
const balance = () => chain.readContract({ address: BASE_USDC, abi, functionName: "balanceOf", args: [payer] });
const [network, block, clock] = await Promise.all([
  chain.getChainId(), chain.getBlock({ blockTag: "latest" }), fetch("https://api.coinbase.com/v2/time", { signal: AbortSignal.timeout(10000) }),
]);
const { data: { epoch: utc } } = await clock.json();
const epoch = Date.parse(clock.headers.get("date"));
if (network !== 8453 || !clock.ok || !Number.isFinite(epoch) || Math.abs(epoch / 1000 - utc) > 2
    || Math.abs(epoch / 1000 - Number(block.timestamp)) > 30) throw new Error("Base or time verification failed");
const tick = performance.now();
Date.now = () => Math.floor(epoch + performance.now() - tick);

const token = await lasoWalletAuth(() => key)();
const authHeaders = { authorization: `Bearer ${token}`, accept: "application/json" };
function cardSummary(value) {
  if (typeof value?.card_id !== "string" || !idPattern.test(value.card_id)) return null;
  return { card_id: value.card_id, status: ["pending", "ready", "failed", "canceled", "cancelled", "queued", "depleted", "expired"].includes(value.status) ? value.status : "unknown",
    usd_amount: value.usd_amount === undefined ? undefined : Number(value.usd_amount),
    available_balance_usd: value.card_details?.available_balance === undefined ? undefined : Number(value.card_details.available_balance) };
}

async function listCards(cardId) {
  const suffix = cardId ? `?${new URLSearchParams({ card_id: cardId })}` : "";
  const response = await fetch(`${origin}/get-card-data${suffix}`, {
    headers: authHeaders, redirect: "error", signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) {
    await response.body?.cancel();
    if (cardId && response.status === 404) return [];
    throw new Error(`Laso card lookup returned HTTP ${response.status}`);
  }
  const payload = await readProviderJson(response);
  if (cardId) return [cardSummary(payload?.card ?? payload)].filter(Boolean);
  if (!Array.isArray(payload?.cards)) throw new Error("Unexpected Laso card list");
  return payload.cards.map(cardSummary).filter(Boolean);
}

if (mode === "preflight") {
  const [cards, before, quote] = await Promise.all([
    listCards(), balance(), fetch(endpoint, { redirect: "error", signal: AbortSignal.timeout(12000) }),
  ]);
  const terms = JSON.parse(Buffer.from(quote.headers.get("payment-required") ?? "", "base64"));
  const offer = terms.accepts.find((candidate) => candidate.network === "eip155:8453"
    && candidate.asset.toLowerCase() === BASE_USDC.toLowerCase() && candidate.scheme === "exact");
  if (quote.status !== 402 || terms.x402Version !== 2 || terms.resource.url !== endpoint
      || offer?.payTo.toLowerCase() !== payee || offer.amount !== amount.toString()) throw new Error("Unexpected Laso quote");
  await quote.body?.cancel();
  console.log(JSON.stringify({ auth: "verified", existing_cards: cards.length, balance_atomic: before.toString(), quote_atomic: offer.amount,
    chain_id: network, payee, resource: terms.resource.url }));
  process.exit(0);
}

if (mode === "issue" || mode === "sign-check") {
  const before = await balance();
  if (before < amount) throw new Error("Less than 5 USDC available on Base");
  const baseline = (await listCards()).map(({ card_id }) => card_id);
  let stage = "before quote request";
  let checkedAuthorization = false;
  const payment = externalBasePayment(() => key, async (url, init) => {
    if (String(url) !== endpoint || init.method !== "GET" || init.redirect !== "error") throw new Error("Unexpected card endpoint");
    const signature = new Headers(init.headers).get("payment-signature");
    if (!signature) {
      stage = "quote validation or signature construction";
      return fetch(url, init);
    }
    stage = "signed envelope validation";
    const { from, to, value, nonce, validBefore } = JSON.parse(Buffer.from(signature, "base64")).payload.authorization;
    if (from.toLowerCase() !== payer || to.toLowerCase() !== payee || value !== amount.toString()
        || !hashPattern.test(nonce) || Number(validBefore) * 1000 <= Date.now()) throw new Error("Unexpected Laso authorization");
    checkedAuthorization = true;
    if (mode === "sign-check") throw new Error("Dry run stops before the signed HTTP request");
    stage = "attempt journal";
    save("attempt", { endpoint, payer, payee, amount_atomic: value, nonce, valid_before: validBefore,
      head_before: block.number.toString(), balance_before: before.toString(), existing_card_ids: baseline });
    const response = await fetch(url, init);
    const rawReceipt = response.headers.get("payment-response") ?? response.headers.get("x-payment-response");
    let receipt;
    try { if (rawReceipt) receipt = JSON.parse(Buffer.from(rawReceipt, "base64")); } catch { /* Card and chain can still be checked. */ }
    const hash = [receipt?.transaction, receipt?.txHash, receipt?.tx_hash].find((candidate) => hashPattern.test(candidate ?? ""));
    const body = await readProviderJson(response.clone(), 65_536).catch(() => null);
    const errorCode = [body?.errorReason, body?.code, receipt?.errorReason].find((value) =>
      typeof value === "string" && /^[a-z][a-z0-9_-]{0,79}$/i.test(value));
    save("http", { status: response.status, receipt_fields: Object.keys(receipt ?? {}),
      reported_success: receipt?.success === true, transaction_hash: hash, error_code: errorCode, card: cardSummary(body?.card) });
    return response;
  });
  try {
    await payment({ url: endpoint, method: "GET", maxUsd: 5, exactUsd: 5, expectedPayTo: payee });
  } catch (error) {
    if (mode === "sign-check" && checkedAuthorization) {
      console.log(JSON.stringify({ checkedAuthorization, paidRequestSent: false }));
      process.exit(0);
    }
    if (!existsSync(artifact("attempt"))) {
      const details = mode === "sign-check" ? `: ${error.name}: ${String(error.message).split("\n")[0].slice(0, 200)}` : "";
      throw new Error(`Laso payment stopped before sending an authorization (${stage})${details}`);
    }
  }
}

const attempt = read("attempt");
if (attempt.endpoint !== endpoint || attempt.payer !== payer || attempt.payee !== payee
    || attempt.amount_atomic !== amount.toString() || !hashPattern.test(attempt.nonce)
    || !Array.isArray(attempt.existing_card_ids)) throw new Error("Saved Laso authorization does not match this test");
const receipt = existsSync(artifact("http")) ? read("http") : {};
const authorization = { from: payer, to: payee, value: amount, nonce: attempt.nonce };
const used = parseAbiItem("event AuthorizationUsed(address indexed authorizer, bytes32 indexed nonce)");
let currentCard;
let transaction;
for (let index = 0; index < 12; index++) {
  const id = receipt.card?.card_id ?? currentCard?.card_id;
  const pending = [
    listCards(id).then((cards) => cards.filter((card) => !attempt.existing_card_ids.includes(card.card_id))),
    (async () => {
      if (transaction) return transaction;
      let hint = receipt.transaction_hash;
      if (!hint) {
        const logs = await chain.getLogs({ address: BASE_USDC, event: used, args: { authorizer: payer, nonce: attempt.nonce }, fromBlock: BigInt(attempt.head_before), strict: true });
        if (logs.length !== 1) return null;
        hint = logs[0].transactionHash;
      }
      return recoverCmcSettlement(chain, authorization, hint);
    })(),
  ];
  const [cards, chainProof] = await Promise.allSettled(pending);
  if (cards.status === "fulfilled" && cards.value.length === 1) currentCard = cards.value[0];
  if (chainProof.status === "fulfilled" && chainProof.value) transaction = chainProof.value;
  if (currentCard?.status === "ready" && transaction) break;
  await delay(2500);
}
const after = await balance();
const before = BigInt(attempt.balance_before);
const transactionReceipt = transaction ? await chain.getTransactionReceipt({ hash: transaction }) : null;
const success = currentCard?.status === "ready" && currentCard.usd_amount === 5 && currentCard.available_balance_usd === 5
  && !!transaction && before - after === amount;
const proof = { success, payer, chain_id: network, paid_atomic: transaction ? amount.toString() : undefined,
  balance_before_atomic: before.toString(), balance_after_atomic: after.toString(),
  transaction_hash: transaction, block: transactionReceipt?.blockNumber.toString(), card: currentCard };
save("proof", proof, "w");
console.log(JSON.stringify(proof, null, 2));
if (!success) process.exitCode = 1;
