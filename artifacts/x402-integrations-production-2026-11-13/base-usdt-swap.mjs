import assert from "node:assert/strict";
import { existsSync, lstatSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { createPublicClient, decodeEventLog, decodeFunctionResult, encodeFunctionData, fallback, getAddress,
  http, keccak256, parseAbi, toHex } from "../../argus/node_modules/viem/_esm/index.js";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { base } from "../../argus/node_modules/viem/_esm/chains/index.js";
import { estimateL1Fee } from "../../argus/node_modules/viem/_esm/op-stack/index.js";

const wallet = getAddress("0x097e3f339d0b023605e12a6b81e2d6cb7571475a");
const usdt = getAddress("0xfde4c96c8593536e31f229ea8f37b2ada2699bb2");
const usdc = getAddress("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913");
const factory = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD";
const pool = "0xD56da2B74bA826f19015E6B7Dd9Dae1903E85DA1";
const quoter = "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a";
const router = "0x2626664c2603336E57B271c5C0b26F421741e481";
const fee = 100;
const amountOut = 4_170_000n;
const inputCeiling = 4_178_964n;
const maxGasPrice = 100_000_000n;
const maxNetworkCost = 50_000_000_000_000n;
const endpoint = "https://mainnet.base.org";
const client = createPublicClient({ chain: base, transport: fallback([endpoint, "https://base-rpc.publicnode.com",
  "https://base.drpc.org"].map((url) => http(url, { retryCount: 0, timeout: 8_000 }))) });
const writer = createPublicClient({ chain: base, transport: http(endpoint, { retryCount: 0, timeout: 12_000 }) });

const erc20 = parseAbi(["function balanceOf(address) view returns (uint256)", "function decimals() view returns (uint8)",
  "function allowance(address,address) view returns (uint256)", "function approve(address,uint256) returns (bool)",
  "event Transfer(address indexed from,address indexed to,uint256 value)",
  "event Approval(address indexed owner,address indexed spender,uint256 value)"]);
const routerAbi = parseAbi(["function factory() view returns (address)",
  "function exactOutputSingle((address tokenIn,address tokenOut,uint24 fee,address recipient,uint256 amountOut,uint256 amountInMaximum,uint160 sqrtPriceLimitX96)) payable returns (uint256)",
  "function multicall(uint256 deadline,bytes[] data) payable returns (bytes[])" ]);
const quoterAbi = parseAbi(["function factory() view returns (address)",
  "function quoteExactOutputSingle((address tokenIn,address tokenOut,uint256 amount,uint24 fee,uint160 sqrtPriceLimitX96)) returns (uint256,uint160,uint32,uint256)"]);
const factoryAbi = parseAbi(["function getPool(address,address,uint24) view returns (address)"]);
const poolAbi = parseAbi(["function factory() view returns (address)", "function token0() view returns (address)",
  "function token1() view returns (address)", "function fee() view returns (uint24)"]);
const same = (a, b) => a.toLowerCase() === b.toLowerCase();
const serial = (value) => JSON.stringify(value, (_key, item) => typeof item === "bigint" ? item.toString() : item, 2);
const evidence = (name) => new URL(`./base-usdt-swap-${name}.json`, import.meta.url);
const write = (name, value) => writeFileSync(evidence(name), `${serial(value)}\n`, { flag: "wx", mode: 0o600 });
const log = (value) => console.log(serial(value));
const read = (address, abi, functionName, args = []) => client.readContract({ address, abi, functionName, args });
const balance = (token, blockNumber) => client.readContract({ address: token, abi: erc20, functionName: "balanceOf",
  args: [wallet], blockNumber });
const allowance = (blockNumber) => client.readContract({ address: usdt, abi: erc20, functionName: "allowance",
  args: [wallet, router], blockNumber });
const approvalData = (value) => encodeFunctionData({ abi: erc20, functionName: "approve", args: [router, value] });
const quote = async (blockNumber) => (await client.simulateContract({ address: quoter, abi: quoterAbi,
  functionName: "quoteExactOutputSingle", blockNumber,
  args: [{ tokenIn: usdt, tokenOut: usdc, amount: amountOut, fee, sqrtPriceLimitX96: 0n }] })).result;

function swapData(maximumIn, deadline) {
  const exactSwap = encodeFunctionData({ abi: routerAbi, functionName: "exactOutputSingle", args: [{ tokenIn: usdt,
    tokenOut: usdc, fee, recipient: wallet, amountOut, amountInMaximum: maximumIn, sqrtPriceLimitX96: 0n }] });
  return encodeFunctionData({ abi: routerAbi, functionName: "multicall", args: [deadline, [exactSwap]] });
}

async function preflight() {
  assert.equal(await client.getChainId(), 8453);
  const block = await client.getBlock({ blockTag: "latest" });
  const [tokenIn, tokenOut, eth, priorAllowance, poolAtFactory, routerFactory, quoterFactory, poolFactory,
    token0, token1, poolFee, inDecimals, outDecimals, quoteResult] = await Promise.all([
    balance(usdt, block.number), balance(usdc, block.number), client.getBalance({ address: wallet, blockNumber: block.number }),
    allowance(block.number), read(factory, factoryAbi, "getPool", [usdt, usdc, fee]), read(router, routerAbi, "factory"),
    read(quoter, quoterAbi, "factory"), read(pool, poolAbi, "factory"), read(pool, poolAbi, "token0"),
    read(pool, poolAbi, "token1"), read(pool, poolAbi, "fee"), read(usdt, erc20, "decimals"),
    read(usdc, erc20, "decimals"), quote(block.number),
  ]);
  assert(same(poolAtFactory, pool) && [routerFactory, quoterFactory, poolFactory].every((x) => same(x, factory)));
  assert(same(token0, usdc) && same(token1, usdt) && poolFee === fee && inDecimals === 6 && outDecimals === 6);
  assert.equal(priorAllowance, 0n);
  assert.equal(tokenOut, 838_158n);
  assert(tokenIn >= inputCeiling && eth >= maxNetworkCost);
  const [quotedIn, , ticks, quoterGas] = quoteResult;
  assert(quotedIn > 0n && quotedIn <= inputCeiling && ticks <= 10);
  // A ten-basis-point tolerance on the fresh exact-output quote, rounded up to an atom.
  const padded = (quotedIn * 1_001n + 999n) / 1_000n;
  const maximumIn = padded < inputCeiling ? padded : inputCeiling;
  const calls = [{ from: wallet, to: usdt, data: approvalData(maximumIn) },
    { from: wallet, to: router, data: swapData(maximumIn, block.timestamp + 300n) },
    { from: wallet, to: usdt, data: approvalData(0n) }];
  const simulated = await client.request({ method: "eth_simulateV1", params: [{ blockStateCalls: [{ calls }],
    validation: false, traceTransfers: false }, toHex(block.number)] });
  const steps = simulated[0]?.calls;
  assert(steps?.length === 3 && steps.every((step) => step.status === "0x1"));
  const [approveGas, swapGas, revokeGas] = steps.map((step) => BigInt(step.gasUsed));
  const [gasPrice, ...dataFees] = await Promise.all([client.getGasPrice(),
    ...calls.map(({ to, data }) => estimateL1Fee(client, { account: wallet, to, data, value: 0n }))]);
  const estimatedNetworkWei = (approveGas + swapGas + revokeGas) * gasPrice + dataFees.reduce((a, b) => a + b, 0n);
  assert(approveGas <= 80_000n && swapGas <= 250_000n && revokeGas <= 80_000n && estimatedNetworkWei <= maxNetworkCost);
  return { chainId: 8453, block: block.number, wallet, usdt, usdc, router, quoter, factory, pool, fee,
    startingUsdtAtomic: tokenIn, startingUsdcAtomic: tokenOut, startingEthWei: eth, existingAllowanceAtomic: priorAllowance,
    amountOutAtomic: amountOut, quotedInAtomic: quotedIn, maximumInAtomic: maximumIn, quoterGas,
    approveGas, swapGas, revokeGas, estimatedNetworkWei };
}

async function checkedReceipt(hash, nonce, to, data) {
  const receipt = await client.waitForTransactionReceipt({ hash, confirmations: 2, checkReplacement: false,
    timeout: 45_000, pollingInterval: 1_500 });
  const [tx, block] = await Promise.all([client.getTransaction({ hash }), client.getBlock({ blockNumber: receipt.blockNumber })]);
  assert(same(receipt.transactionHash, hash) && same(tx.hash, hash) && same(receipt.blockHash, block.hash));
  assert(same(tx.from, wallet) && same(tx.to, to) && tx.input === data && tx.value === 0n && tx.nonce === nonce);
  return receipt;
}

let accountedBudget = 0n;
async function send(account, name, to, data, gasCeiling) {
  const [minedNonce, pendingNonce, gasEstimate, gasPrice, l1Fee] = await Promise.all([
    client.getTransactionCount({ address: wallet, blockTag: "latest" }),
    client.getTransactionCount({ address: wallet, blockTag: "pending" }),
    client.estimateGas({ account: wallet, to, data, prepare: false }), client.getGasPrice(),
    estimateL1Fee(client, { account: wallet, to, data, value: 0n }),
  ]);
  assert.equal(minedNonce, pendingNonce);
  const gas = (gasEstimate * 12n + 9n) / 10n;
  const maxFeePerGas = gasPrice * 3n;
  const maxPriorityFeePerGas = 1_000_000n;
  const upperEstimate = gas * maxFeePerGas + 3n * l1Fee;
  assert(gas <= gasCeiling && maxFeePerGas <= maxGasPrice && maxFeePerGas >= maxPriorityFeePerGas);
  accountedBudget += upperEstimate;
  assert(accountedBudget <= maxNetworkCost && await client.getBalance({ address: wallet }) >= upperEstimate);
  const serializedTransaction = await account.signTransaction({ type: "eip1559", chainId: 8453, nonce: minedNonce,
    to, data, gas, maxFeePerGas, maxPriorityFeePerGas, value: 0n });
  const hash = keccak256(serializedTransaction);
  write(`${name}-intent`, { hash, nonce: minedNonce, to, gasEstimate, gas, maxFeePerGas, maxPriorityFeePerGas,
    estimatedL1FeeWei: l1Fee, estimatedBudgetWei: upperEstimate });
  log({ phase: name, signedHash: hash });
  // If the submission times out, only reconcile this signed hash. Never sign or submit another transaction.
  try {
    const reported = await writer.request({ method: "eth_sendRawTransaction", params: [serializedTransaction] }, { retryCount: 0 });
    assert(same(reported, hash));
    log({ phase: name, submission: "accepted", hash });
  } catch {
    log({ phase: name, submission: "uncertain", hash });
  }
  const receipt = await checkedReceipt(hash, minedNonce, to, data);
  const facts = { phase: name, hash, nonce: minedNonce, status: receipt.status, block: receipt.blockNumber,
    blockHash: receipt.blockHash, gasUsed: receipt.gasUsed, effectiveGasPrice: receipt.effectiveGasPrice,
    l1FeeWei: receipt.l1Fee ?? null };
  write(`${name}-receipt`, facts);
  log(facts);
  return receipt;
}

function events(receipt, token, name) {
  return receipt.logs.filter((log) => same(log.address, token)).flatMap((log) => {
    try {
      const decoded = decodeEventLog({ abi: erc20, eventName: name, data: log.data, topics: log.topics });
      return decoded.eventName === name ? [decoded.args] : [];
    } catch { return []; }
  });
}

async function main() {
  assert(["preflight", "execute"].includes(process.argv[2]));
  const plan = await preflight();
  log(plan);
  if (process.argv[2] === "preflight") return;
  assert.equal(await writer.getChainId(), 8453);
  const path = join(homedir(), ".aicom-pov-buyer.json");
  const metadata = lstatSync(path);
  assert(metadata.isFile() && (metadata.mode & 0o077) === 0 && metadata.uid === process.getuid());
  const saved = JSON.parse(readFileSync(path, "utf8"));
  const account = privateKeyToAccount(saved.private_key.startsWith("0x") ? saved.private_key : `0x${saved.private_key}`);
  delete saved.private_key;
  assert(same(account.address, wallet));
  write("preflight", plan);

  const approved = await send(account, "approve", usdt, approvalData(plan.maximumInAtomic), 80_000n);
  assert.equal(approved.status, "success");

  let minedSwap = false;
  try {
    assert.equal(await allowance(approved.blockNumber), plan.maximumInAtomic);
    assert(events(approved, usdt, "Approval").some((x) => same(x.owner, wallet) && same(x.spender, router)
      && x.value === plan.maximumInAtomic));
    const block = await client.getBlock({ blockTag: "latest" });
    const [refreshedIn] = await quote(block.number);
    assert(refreshedIn > 0n && refreshedIn <= plan.maximumInAtomic);
    const data = swapData(plan.maximumInAtomic, block.timestamp + 300n);
    const result = await client.call({ account: wallet, to: router, data });
    const [returned] = decodeFunctionResult({ abi: routerAbi, functionName: "multicall", data: result.data });
    const exactIn = decodeFunctionResult({ abi: routerAbi, functionName: "exactOutputSingle", data: returned });
    assert(exactIn > 0n && exactIn <= plan.maximumInAtomic);
    const receipt = await send(account, "swap", router, data, 250_000n);
    minedSwap = true;
    assert.equal(receipt.status, "success");
    const debits = events(receipt, usdt, "Transfer").filter((x) => same(x.from, wallet));
    const credits = events(receipt, usdc, "Transfer").filter((x) => same(x.to, wallet));
    assert(debits.length === 1 && same(debits[0].to, pool) && debits[0].value > 0n && debits[0].value <= plan.maximumInAtomic);
    assert(credits.length === 1 && same(credits[0].from, pool) && credits[0].value === amountOut);
    const [afterUsdt, afterUsdc, remaining] = await Promise.all([balance(usdt, receipt.blockNumber),
      balance(usdc, receipt.blockNumber), allowance(receipt.blockNumber)]);
    assert.equal(afterUsdt, plan.startingUsdtAtomic - debits[0].value);
    assert.equal(afterUsdc, plan.startingUsdcAtomic + amountOut);
    const proof = { swap: receipt.transactionHash, block: receipt.blockNumber, blockHash: receipt.blockHash,
      paidUsdtAtomic: debits[0].value, receivedUsdcAtomic: credits[0].value, balanceUsdtAtomic: afterUsdt,
      balanceUsdcAtomic: afterUsdc, remainingAllowanceAtomic: remaining };
    write("verified", proof);
    log(proof);
  } finally {
    if (!existsSync(evidence("swap-intent")) || minedSwap) {
      const remaining = await allowance();
      if (remaining > 0n) {
        assert(remaining <= plan.maximumInAtomic);
        const reset = await send(account, "revoke", usdt, approvalData(0n), 80_000n);
        assert.equal(reset.status, "success");
      }
      assert.equal(await allowance(), 0n);
      const completion = { finalAllowanceAtomic: 0, estimatedNetworkBudgetWei: accountedBudget };
      write("completed", completion);
      log(completion);
    }
  }
}

try { await main(); }
catch (error) {
  console.error(`Swap operation stopped: ${error.name}${error.code ? ` (${error.code})` : ""}`);
  process.exitCode = 1;
}
