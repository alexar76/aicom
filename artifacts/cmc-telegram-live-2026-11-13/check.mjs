import assert from "node:assert/strict";

const BASELINE_BLOCK = 57_063_721n;
const BASELINE_BALANCE = 10_000n;
const EXPECTED_AMOUNT = 10_000n;
const BASE_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913";
const PAYER = "0x1cdb27372ed3d5d37080a5a3256512b17ea321bc";
const PAYEE = "0x3c5f3a6ce224bb89d72f5eb4232ecc27f67b3eea";
const AUTH_USED = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5";
const TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const BASE_RPC = ["https://base-rpc.publicnode.com", "https://mainnet.base.org", "https://base.drpc.org"];
const MONITOR = "https://monitor.modelmarket.dev/api/provider-events";
const BASELINE_MONITOR = { succeeded: 0, failed: 0, attempted: 0 };
const HASH = /^0x[0-9a-f]{64}$/i;
const MAX_SCAN_BLOCKS = 14_400n;
const SCAN_CHUNK = 1_000n;

const hex = value => `0x${value.toString(16)}`;
const word = value => value.slice(2).toLowerCase().padStart(64, "0");
const topic = address => `0x${word(address)}`;
const same = (a, b) => typeof a === "string" && a.toLowerCase() === b.toLowerCase();

function rpcFor(url) {
  let id = 0;
  return async (method, params = []) => {
    const requestId = ++id;
    const response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: requestId, method, params }),
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    assert(response.ok, `${method}: HTTP ${response.status}`);
    const json = await response.json();
    assert(json.id === requestId && !json.error && Object.hasOwn(json, "result"), `${method}: invalid or failed RPC response`);
    return json.result;
  };
}

async function readMonitor() {
  try {
    const response = await fetch(MONITOR, { redirect: "error", signal: AbortSignal.timeout(10_000) });
    assert(response.ok, `Monitor HTTP ${response.status}`);
    const payload = await response.json();
    assert.equal(payload.state, "ok");
    assert.equal(payload.window_seconds, 86_400);
    const provider = payload.providers.find(entry => entry.id === "coinmarketcap");
    const row = provider?.operations.find(entry => entry.source === "argus" && entry.operation === "quotes");
    assert(row, "CMC quote counters are missing");
    const counts = {};
    for (const key of Object.keys(BASELINE_MONITOR)) {
      assert(Number.isSafeInteger(row[key]) && row[key] >= 0, "Invalid Monitor counter");
      counts[key] = row[key];
    }
    return {
      url: MONITOR,
      stream: "coinmarketcap/argus/quotes",
      window_seconds: payload.window_seconds,
      baseline: BASELINE_MONITOR,
      current: counts,
      one_new_success: counts.succeeded === 1 && counts.attempted === 0 && counts.failed === 0,
      correlation: "aggregate only; event does not include a transaction hash or nonce",
    };
  } catch (error) {
    return { url: MONITOR, unavailable: error.message };
  }
}

async function readToken(rpc, callData, block) {
  const value = await rpc("eth_call", [{ to: BASE_USDC, data: callData }, hex(block)]);
  assert(HASH.test(value), "USDC view returned invalid data");
  return BigInt(value);
}

function balanceAt(rpc, block) {
  return readToken(rpc, `0x70a08231${word(PAYER)}`, block);
}

function authorizationAt(rpc, nonce, block) {
  return readToken(rpc, `0xe94a0102${word(PAYER)}${word(nonce)}`, block);
}

async function scanAuthorizations(rpc, head) {
  assert(head - BASELINE_BLOCK <= MAX_SCAN_BLOCKS, "Scan window exceeds 14,400 blocks; supply the transaction hash");
  const results = [];
  for (let from = BASELINE_BLOCK + 1n; from <= head; from += SCAN_CHUNK) {
    const end = from + SCAN_CHUNK - 1n;
    const to = end < head ? end : head;
    const logs = await rpc("eth_getLogs", [{ address: BASE_USDC, fromBlock: hex(from), toBlock: hex(to), topics: [AUTH_USED, topic(PAYER)] }]);
    assert(Array.isArray(logs), "Invalid authorization log response");
    for (const log of logs) {
      assert(isAuthorization(log) && BigInt(log.blockNumber) >= from && BigInt(log.blockNumber) <= to, "Invalid authorization log returned by scan");
      results.push(log);
    }
  }
  return results;
}

function isAuthorization(log) {
  return log?.removed === false && same(log.address, BASE_USDC) && log.topics?.length === 3
    && same(log.topics[0], AUTH_USED) && same(log.topics[1], topic(PAYER)) && HASH.test(log.topics[2])
    && log.data === "0x" && HASH.test(log.transactionHash) && HASH.test(log.blockHash);
}

function isPayerTransfer(log) {
  return log?.removed === false && same(log.address, BASE_USDC) && log.topics?.length === 3
    && same(log.topics[0], TRANSFER) && same(log.topics[1], topic(PAYER));
}

function belongsToReceipt(log, receipt) {
  return same(log.transactionHash, receipt.transactionHash) && same(log.blockHash, receipt.blockHash)
    && BigInt(log.blockNumber) === BigInt(receipt.blockNumber);
}

async function inspect(rpcUrl, requestedHash) {
  const rpc = rpcFor(rpcUrl);
  assert.equal(BigInt(await rpc("eth_chainId")), 8453n, "Wrong chain");
  const head = BigInt(await rpc("eth_blockNumber"));
  assert(head >= BASELINE_BLOCK, "RPC has not reached the baseline");
  const [before, after] = await Promise.all([balanceAt(rpc, BASELINE_BLOCK), balanceAt(rpc, head)]);
  assert.equal(before, BASELINE_BALANCE, "Baseline wallet balance does not match");
  const baseline = { block: String(BASELINE_BLOCK), balance_atomic: String(before) };
  const current = { block: String(head), balance_atomic: String(after), balance_delta_atomic: String(after - before) };
  const traces = requestedHash ? undefined : await scanAuthorizations(rpc, head);
  assert(!traces || traces.length <= 1, "Multiple new payer authorizations; cannot tie window to one payment");
  const trace = traces?.[0];
  const hash = requestedHash || trace?.transactionHash;
  if (!hash) return { rpc: rpcUrl, status: after === before ? "no_new_authorization" : "unexpected_balance_change", baseline, current, new_authorizations: 0 };

  const receipt = await rpc("eth_getTransactionReceipt", [hash]);
  if (!receipt) return { rpc: rpcUrl, status: "receipt_not_visible", transaction_hash: hash, baseline, current };
  assert.equal(BigInt(receipt.status), 1n, "Transaction reverted");
  assert(same(receipt.transactionHash, hash) && HASH.test(receipt.blockHash), "Invalid receipt identity");
  const blockNumber = BigInt(receipt.blockNumber);
  assert(blockNumber > BASELINE_BLOCK && blockNumber <= head, "Receipt is outside the fresh observation window");
  const authorizations = receipt.logs.filter(isAuthorization);
  assert.equal(authorizations.length, 1, "Receipt must consume exactly one payer nonce");
  const [authorization] = authorizations;
  assert(belongsToReceipt(authorization, receipt), "Authorization log does not belong to receipt");
  if (traces) {
    assert(trace && same(trace.topics[2], authorization.topics[2]) && belongsToReceipt(trace, receipt)
      && BigInt(trace.logIndex) === BigInt(authorization.logIndex), "Receipt nonce disagrees with fresh log scan");
  }
  const transfers = receipt.logs.filter(isPayerTransfer);
  assert.equal(transfers.length, 1, "Receipt must contain exactly one USDC transfer from payer");
  const [transfer] = transfers;
  assert(belongsToReceipt(transfer, receipt) && BigInt(transfer.logIndex) === BigInt(authorization.logIndex) + 1n
    && same(transfer.topics[2], topic(PAYEE)) && HASH.test(transfer.data) && BigInt(transfer.data) === EXPECTED_AMOUNT,
    "Adjacent USDC transfer does not match the pinned CMC recipient and amount");
  const nonce = authorization.topics[2];
  const [canonical, finalized, unused, used] = await Promise.all([
    rpc("eth_getBlockByNumber", [hex(blockNumber), false]),
    rpc("eth_getBlockByNumber", ["finalized", false]),
    authorizationAt(rpc, nonce, BASELINE_BLOCK),
    authorizationAt(rpc, nonce, head),
  ]);
  assert(canonical && BigInt(canonical.number) === blockNumber && same(canonical.hash, receipt.blockHash), "Receipt is not canonical");
  assert(finalized && HASH.test(finalized.hash), "Invalid finalized head");
  assert.equal(unused, 0n, "Nonce was already used at preflight baseline");
  assert.equal(used, 1n, "Nonce is not marked as used after the payment");
  const finalBlock = BigInt(finalized.number);
  return {
    rpc: rpcUrl,
    status: finalBlock >= blockNumber ? "transfer_finalized" : "transfer_canonical_awaiting_finality",
    transaction_hash: hash,
    block: String(blockNumber),
    block_hash: receipt.blockHash,
    confirmations: String(head - blockNumber + 1n),
    finalized_head: String(finalBlock),
    nonce,
    nonce_unused_at_baseline: true,
    nonce_used_at_observed_head: true,
    authorization_log_index: String(BigInt(authorization.logIndex)),
    transfer_log_index: String(BigInt(transfer.logIndex)),
    new_authorizations: traces?.length ?? null,
    amount_atomic: String(EXPECTED_AMOUNT),
    exact_balance_delta: before - after === EXPECTED_AMOUNT,
    baseline,
    current,
  };
}

async function inspectSafely(rpc, hash) {
  try { return await inspect(rpc, hash); }
  catch (error) { return { rpc, status: "verification_failed", error: error.message }; }
}

const [argument, ...extraArguments] = process.argv.slice(2);
if (argument === "--help" && !extraArguments.length) {
  console.log("Usage: node artifacts/cmc-telegram-live-2026-11-13/check.mjs [transaction-hash]");
} else if (extraArguments.length || (argument && !HASH.test(argument))) {
  console.error("Provide one Base transaction hash, or omit it to scan for new payer authorizations.");
  process.exitCode = 2;
} else {
  const monitorPromise = readMonitor();
  let rpcs = await Promise.all(BASE_RPC.map(rpc => inspectSafely(rpc, argument)));
  const discovered = new Set(rpcs.filter(result => result.status.startsWith("transfer_")).map(result => result.transaction_hash.toLowerCase()));
  if (!argument && discovered.size === 1) {
    const [hash] = discovered;
    rpcs = await Promise.all(rpcs.map(async result => {
      if (!/^eth_getLogs:/.test(result.error ?? "")) return result;
      return { ...await inspectSafely(result.rpc, hash), log_scan_unavailable: result.error };
    }));
  }
  const verified = rpcs.filter(result => result.status.startsWith("transfer_"));
  const hashes = new Set(verified.map(result => result.transaction_hash.toLowerCase()));
  const multipleAuthorizations = rpcs.some(result => result.error?.startsWith("Multiple new payer authorizations"));
  const proofsAgree = !multipleAuthorizations && hashes.size === 1
    && new Set(verified.map(result => `${result.block_hash}:${result.nonce}`.toLowerCase())).size === 1;
  console.log(JSON.stringify({
    checked_at: new Date().toISOString(),
    chain_id: 8453,
    token: BASE_USDC,
    payer: PAYER,
    recipient: PAYEE,
    transaction_hash: proofsAgree ? verified[0].transaction_hash : null,
    canonical_rpc_confirmations: proofsAgree ? verified.length : 0,
    finalized_rpc_confirmations: proofsAgree ? verified.filter(result => result.status === "transfer_finalized").length : 0,
    rpcs,
    monitor: await monitorPromise,
  }, null, 2));
  if (multipleAuthorizations || (verified.length > 0 && !proofsAgree) || (argument && !proofsAgree) || verified.some(result => !result.exact_balance_delta)
    || rpcs.every(result => result.status === "verification_failed") || rpcs.some(result => result.status === "unexpected_balance_change")) {
    process.exitCode = 1;
  }
}
