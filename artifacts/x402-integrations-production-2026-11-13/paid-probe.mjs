import { readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { performance } from "node:perf_hooks";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { createPublicClient, fallback, http } from "../../argus/node_modules/viem/_esm/index.js";
import { base } from "../../argus/node_modules/viem/_esm/chains/index.js";
import { x402Client } from "../../argus/node_modules/@x402/core/dist/esm/client/index.mjs";
import { registerExactEvmScheme } from "../../argus/node_modules/@x402/evm/dist/esm/exact/client/index.mjs";
import { wrapFetchWithPayment } from "../../argus/node_modules/@x402/fetch/dist/esm/index.mjs";
import { CMC_QUOTES, externalBasePayment, externalTavilyPayment } from "../../argus/dist/economy/external-payment.js";
import { buildCoinMarketCapTool } from "../../argus/dist/tools/cmc.js";
import { buildExternalResearchTools } from "../../argus/dist/tools/external-research.js";
import { recoverCmcSettlement } from "../../argus/dist/economy/cmc-settlement.js";

const provider = process.argv[2];
if (provider !== "cmc" && provider !== "tavily") throw new Error("Choose one provider: cmc or tavily");
const retry = process.argv[3] === "retry-unused";
const official = process.argv[3] === "official-sdk";
const ownerCanary = process.argv[3] === "owner-canary";
if ((retry || official) && provider !== "tavily") throw new Error("Only an expired, unused Tavily authorization can be retried");
if (ownerCanary && provider !== "cmc") throw new Error("The dedicated owner wallet is for CMC only");
const payer = ownerCanary ? "0x1cdb27372ed3d5d37080a5a3256512b17ea321bc" : "0x097e3f339d0b023605e12a6b81e2d6cb7571475a";
const cmcRecipient = "0x3c5f3a6ce224bb89d72f5eb4232ecc27f67b3eea";
const endpoint = provider === "cmc" ? `${CMC_QUOTES}?id=1,1027` : "https://x402.tavily.com/search";
const runName = ownerCanary ? "cmc-owner-canary" : official ? "tavily-sdk" : retry ? "tavily-retry" : provider;
const artifact = (suffix) => new URL(`./${runName}-${suffix}.json`, import.meta.url);
function write(suffix, value) {
  writeFileSync(artifact(suffix), `${JSON.stringify(value, null, 2)}\n`, { flag: "wx", mode: 0o600 });
}

const keyFile = ownerCanary ? "/private/tmp/aicom-cmc-owner-pilot-20261113/signer.json" : join(homedir(), ".aicom-pov-buyer.json");
if (statSync(keyFile).mode & 0o077) throw new Error("Expected an owner-only test wallet file");
const wallet = JSON.parse(readFileSync(keyFile, "utf8"));
const key = wallet.private_key.startsWith("0x") ? wallet.private_key : `0x${wallet.private_key}`;
delete wallet.private_key;
if (privateKeyToAccount(key).address.toLowerCase() !== payer) throw new Error("Unexpected test wallet");

const clockResponse = await fetch("https://api.coinbase.com/v2/time", { signal: AbortSignal.timeout(10000) });
const baseResponse = await fetch("https://mainnet.base.org", {
  method: "POST", headers: { "content-type": "application/json" }, signal: AbortSignal.timeout(10000),
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getBlockByNumber", params: ["latest", false] }),
});
const time = await clockResponse.json();
const baseBlock = (await baseResponse.json()).result;
const epoch = Date.parse(clockResponse.headers.get("date"));
if (!clockResponse.ok || !baseResponse.ok || !Number.isFinite(epoch) || Math.abs(epoch / 1000 - time.data?.epoch) > 2
    || Math.abs(epoch / 1000 - Number(baseBlock?.timestamp)) > 30) throw new Error("Coinbase and Base time disagree");
if (retry || official) {
  const priorFile = official ? "tavily-retry-chain.json" : "tavily-chain.json";
  const prior = JSON.parse(readFileSync(new URL(`./${priorFile}`, import.meta.url), "utf8"));
  if (prior.authorization_used !== false || prior.head_time <= prior.auth_valid_before) {
    throw new Error("The previous Tavily authorization may still settle");
  }
}
const started = performance.now();
const hostOffsetSeconds = Math.round((Date.now() - epoch) / 1000);
Date.now = () => Math.floor(epoch + performance.now() - started);

let sent = false;
async function observedFetch(url, init) {
  if ((url instanceof Request ? url.url : String(url)) !== endpoint) throw new Error("Unexpected payment destination");
  const headers = new Headers(url instanceof Request ? url.headers : init.headers);
  const payment = headers.get("payment-signature");
  if (payment) {
    if (sent) throw new Error("Payment already attempted");
    const authorization = JSON.parse(Buffer.from(payment, "base64")).payload.authorization;
    const { from, to, value, nonce, validBefore } = authorization;
    if (from.toLowerCase() !== payer || (provider === "cmc" && to.toLowerCase() !== cmcRecipient)
        || value !== "10000" || Number(validBefore) * 1000 <= Date.now()) {
      throw new Error("Unexpected payment terms");
    }
    write("attempt", { endpoint, chain_id: 8453, payer, recipient: to.toLowerCase(), amount_atomic: value,
      authorization_nonce: nonce, valid_before: validBefore, host_offset_seconds: hostOffsetSeconds,
      authorized_at: new Date(Date.now()).toISOString() });
    sent = true;
  }
  const response = await fetch(url, init);
  if (sent && payment) {
    const header = response.headers.get("payment-response") ?? response.headers.get("x-payment-response");
    const receipt = header ? JSON.parse(Buffer.from(header, "base64")) : null;
    const requiredHeader = response.headers.get("payment-required");
    const nextQuote = requiredHeader ? JSON.parse(Buffer.from(requiredHeader, "base64")) : null;
    const errorBody = response.status === 402 && Number(response.headers.get("content-length")) < 8192
      ? await response.clone().json().catch(() => null) : null;
    write("http", { status: response.status, receipt_fields: receipt && Object.keys(receipt),
      receipt: receipt && { success: receipt.success, transaction: receipt.transaction,
        network: receipt.network, payer: receipt.payer, amount: receipt.amount },
      provider_error: nextQuote?.error ?? errorBody?.error, provider_error_code: errorBody?.code ?? errorBody?.errorCode,
      provider_message: errorBody?.message });
  }
  return response;
}

if (official) {
  const signer = privateKeyToAccount(key);
  const client = registerExactEvmScheme(new x402Client(), { signer, networks: ["eip155:8453"] });
  client.onBeforePaymentCreation(({ paymentRequired, selectedRequirements: offer }) => {
    if (paymentRequired.x402Version !== 2 || paymentRequired.resource?.url !== endpoint || offer.network !== "eip155:8453"
        || offer.scheme !== "exact" || offer.amount !== "10000" || offer.maxTimeoutSeconds !== 60
        || offer.asset.toLowerCase() !== "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
        || offer.extra?.name !== "USD Coin" || offer.extra?.version !== "2"
        || (offer.extra?.assetTransferMethod ?? "eip3009") !== "eip3009") return { abort: true, reason: "Unexpected Tavily quote" };
  });
  const response = await wrapFetchWithPayment(observedFetch, client)(endpoint, {
    method: "POST", redirect: "error", signal: AbortSignal.timeout(90000),
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ query: "IETF RFC 9110 status code 402 Payment Required", search_depth: "advanced", max_results: 2 }),
  });
  const data = response.ok ? await response.json() : null;
  const links = (data?.results ?? []).map(({ title, url }) => ({ title, url }));
  write("tool", { method: "documented x402 SDK wrapper", ok: response.ok, status: response.status, links });
  console.log(JSON.stringify({ provider, sent, status: response.status, links }));
  if (!response.ok) process.exitCode = 1;
} else {
  const rpcUrls = ["https://base-rpc.publicnode.com", "https://mainnet.base.org", "https://base.drpc.org"];
  const transport = fallback(rpcUrls.map((url) => http(url, { timeout: 4000, retryCount: 0 })), { retryCount: 0 });
  const chain = ownerCanary ? createPublicClient({ chain: base, transport }) : undefined;
  const pay = externalBasePayment(() => key, observedFetch, chain);
  const tavilyPay = externalTavilyPayment(() => key, observedFetch);
  const tool = provider === "cmc" ? buildCoinMarketCapTool(pay, cmcRecipient) : buildExternalResearchTools({ tavilyPay })[0];
  const args = provider === "cmc" ? { ids: [1, 1027] } : { query: "IETF RFC 9110 status code 402 Payment Required", limit: 2 };
  const denied = await tool.run(args, { approved: false });
  if (denied.ok || sent) throw new Error("The tool accepted an unapproved payment");
  const result = await tool.run(args, { approved: true });
  let transaction;
  if (chain && sent) {
    const attempt = JSON.parse(readFileSync(artifact("attempt"), "utf8"));
    transaction = await recoverCmcSettlement(chain, { from: payer, to: cmcRecipient,
      nonce: attempt.authorization_nonce, value: BigInt(attempt.amount_atomic) }).catch(() => null);
  }
  write(sent ? "tool" : "tool-unpaid", { tool: tool.def.name, approval_check: denied.ok === false, transaction, result });
  console.log(JSON.stringify({ provider, sent, ok: result.ok, result: result.content }));
  if (!result.ok || (ownerCanary && !transaction)) process.exitCode = 1;
}
