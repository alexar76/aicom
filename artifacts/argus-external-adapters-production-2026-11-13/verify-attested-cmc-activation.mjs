// Run inside the live ARGUS container from /app. No signing, provider call or Telegram message.
import assert from "node:assert/strict";
import { parseAbi } from "viem";
import { loadConfig } from "./dist/config.js";
import { Runtime } from "./dist/runtime.js";
import { telegramEnabled } from "./dist/cli/commands/channels.js";
import { needsApproval } from "./dist/core/agent.js";
import { requiresExactApproval } from "./dist/core/approval-preview.js";
import { buildChainContext } from "./dist/ecosystem/networks.js";
import { BASE_USDC } from "./dist/economy/cmc-settlement.js";

const wallet = "0x1cdb27372ed3d5d37080a5a3256512b17ea321bc";
const recipient = "0x3c5f3a6ce224bb89d72f5eb4232ecc27f67b3eea";
const log = { info() {}, warn() {}, error() {}, debug() {}, child() { return this; } };
const { config } = loadConfig();
assert.equal(config.mode, "live");
assert.equal(config.cryptoEnabled, true);
assert(telegramEnabled(config.stateDir), "Telegram must be enabled");
const owner = process.env.ARGUS_TELEGRAM_OWNER_ID?.trim() || config.telegram.ownerId;
assert(/^[1-9]\d*$/.test(String(owner)), "Telegram owner must be pinned");
assert(!process.env.ARGUS_HTTP_TOKEN?.trim(), "HTTP /ask must stay disabled");
assert(process.env.ARGUS_CMC_PAY_TO?.toLowerCase() === recipient, "Unexpected CMC recipient");

const chain = buildChainContext({ mode: "live", log });
const nativeFetch = globalThis.fetch;
let providerCalls = 0;
let fixtureRuntime;
try {
  globalThis.fetch = async () => { providerCalls++; throw new Error("Provider calls prohibited in verification"); };
  const state = { config, chain };
  const tools = Runtime.prototype.assistantTools.call(state);
  fixtureRuntime = state;
  const vendors = tools.filter(({ def }) => /^(?:cmc_|tavily_|laso_|browserbase_|chuhching_)/.test(def.name));
  assert.deepEqual(vendors.map(({ def }) => def.name), ["cmc_buy_quotes"]);
  const [cmc] = vendors;
  assert(requiresExactApproval(cmc.def.name) && needsApproval(cmc.def.name, cmc.source, config.warden));
  assert.equal((await cmc.run({ ids: [1] }, { log })).ok, false);
  assert.equal(providerCalls, 0);
} finally {
  globalThis.fetch = nativeFetch;
}
assert(fixtureRuntime?._externalWallet?.address.toLowerCase() === wallet, "Unexpected CMC signer address");
const http = await fetch(`http://127.0.0.1:${config.http.port}/ask`, {
  method: "POST", headers: { "content-type": "application/json" }, body: "{}",
});
assert.equal(http.status, 503);
await http.body?.cancel();
const chainId = await chain.publicClient.getChainId();
assert.equal(chainId, 8453);
const amount = await chain.publicClient.readContract({
  address: BASE_USDC, abi: parseAbi(["function balanceOf(address account) view returns (uint256)"]),
  functionName: "balanceOf", args: [wallet],
});
assert.equal(amount, 10000n, "Dedicated CMC signer balance differed from expected 0.01 USDC");
console.log(JSON.stringify({ mode: config.mode, chainId, telegramEnabled: true, telegramOwnerPinned: true,
  tool: "cmc_buy_quotes", exactPrivateOwnerApproval: true, publicHttpAskStatus: http.status,
  otherPaidVendorTools: [], noApprovalProviderCalls: providerCalls, signer: wallet, recipient,
  signerBalanceAtomic: String(amount), noPaymentOrTelegramMessage: true }));
