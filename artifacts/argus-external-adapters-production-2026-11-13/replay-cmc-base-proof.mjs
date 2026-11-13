// Verifies a known, public CMC canary from a narrow historical window without contacting CMC or signing.
// Run from /app with: node --input-type=module - < replay-cmc-base-proof.mjs
import assert from "node:assert/strict";
import { buildChainContext } from "./dist/ecosystem/networks.js";
import { recoverCmcSettlement } from "./dist/economy/cmc-settlement.js";

const proof = {
  from: "0x097e3f339d0b023605e12a6b81e2d6cb7571475a",
  to: "0x3c5f3a6ce224bb89d72f5eb4232ecc27f67b3eea",
  value: 10000n,
  nonce: "0xe77dec8d3b46476a865eedfaae3143a4d8e031f2009a63d2614004a5acc58b7c",
};
const blockNumber = 56857679n;
const tx = "0x78c7d94a4702242305a952fd341d6f532834036d2bc02dff9e4b300d1502ef8c";
const silent = { info() {}, warn() {}, error() {}, debug() {} };
const { publicClient } = buildChainContext({ mode: "live", log: silent });
assert((await publicClient.getBlockNumber()) > blockNumber + 1n);
const historicalWindow = { ...publicClient, getBlockNumber: async () => blockNumber + 2n };
assert.equal(await recoverCmcSettlement(historicalWindow, proof), tx);
assert.equal(await recoverCmcSettlement(historicalWindow, { ...proof, value: 9999n }), null);
console.log(JSON.stringify({ source: "production viem reader, fixed historical window", chainId: 8453, amountAtomic: String(proof.value),
  blockNumber: String(blockNumber), transaction: tx, authorizationNonce: proof.nonce, mismatchedAmountRejected: true, readOnly: true }));

const hint = "0x24f175a2f0c56d9e1f3d3e0933a19d7964d057d22d761db0e468ec2cdc25c1d3";
const directProof = {
  ...proof,
  from: "0x1cdb27372ed3d5d37080a5a3256512b17ea321bc",
  nonce: "0xc05f257314f6f4284a2a2cdcc1266bc42d29f593aef7cfd3a7f45cc7b1be7ddd",
};
const directRead = { ...publicClient, getLogs: () => { throw new Error("Hash-hint verification must never scan logs"); } };
assert.equal(await recoverCmcSettlement(directRead, directProof, hint), hint);
assert.equal(await recoverCmcSettlement(directRead, { ...directProof, nonce: proof.nonce }, hint), null);
console.log(JSON.stringify({ source: "production viem reader, direct hash hint", chainId: 8453,
  amountAtomic: String(directProof.value), blockNumber: "56863462", transaction: hint,
  authorizationNonce: directProof.nonce, wrongNonceRejected: true, logScanUsed: false, readOnly: true }));
