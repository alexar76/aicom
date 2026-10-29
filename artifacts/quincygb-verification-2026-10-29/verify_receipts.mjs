// Public RPC only; no key or signer is loaded.
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../../scripts/delivery-survey/package.json', import.meta.url));
const { createPublicClient, http, parseAbi, parseEventLogs } = require('viem');
const { base } = require('viem/chains');
const rpc = createPublicClient({ chain: base, transport: http('https://mainnet.base.org', { timeout: 20000, retryCount: 1 }) });
const out = new URL('./', import.meta.url);
const rows = readFileSync(new URL('paid-results.jsonl', out), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
const token = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913';
const payer = '0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a';
const payee = '0x097f9685d1e0752bf8b02d61e5ce9be7ea0fba7f';
const abi = parseAbi(['event Transfer(address indexed from, address indexed to, uint256 value)', 'event AuthorizationUsed(address indexed authorizer, bytes32 indexed nonce)']);
const verified = await Promise.all(rows.map(async row => {
  const receipt = await rpc.getTransactionReceipt({ hash: row.settle.transaction });
  const tokenLogs = receipt.logs.filter(log => log.address.toLowerCase() === token);
  const events = parseEventLogs({ abi, logs: tokenLogs, strict: false });
  const transfer = events.find(e => e.eventName === 'Transfer'
    && e.args.from?.toLowerCase() === payer && e.args.to?.toLowerCase() === payee
    && String(e.args.value) === row.signed.value);
  const authorization = events.find(e => e.eventName === 'AuthorizationUsed'
    && e.args.authorizer?.toLowerCase() === payer && e.args.nonce?.toLowerCase() === row.signed.nonce.toLowerCase());
  writeFileSync(new URL(`${row.call_id}-tx-receipt.json`, out), JSON.stringify(receipt, (_k, v) => typeof v === 'bigint' ? String(v) : v, 2) + '\n');
  return { call_id: row.call_id, transaction: row.settle.transaction, status: receipt.status,
    block_number: String(receipt.blockNumber), value_atomic: row.signed.value,
    transfer_matches_approved_payment: Boolean(transfer), authorization_nonce_matches: Boolean(authorization),
    verified: receipt.status === 'success' && Boolean(transfer) && Boolean(authorization) };
}));
const result = { verified_at_utc: new Date().toISOString(), payer, payee, token,
  total_usdc: (Number(verified.reduce((s, r) => s + BigInt(r.value_atomic), 0n)) / 1e6).toFixed(6),
  total_atomic: String(verified.reduce((s, r) => s + BigInt(r.value_atomic), 0n)), records: verified };
writeFileSync(new URL('receipt-verification.json', out), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result, null, 2));
if (verified.length !== 3 || verified.some(r => !r.verified) || result.total_atomic !== '60000') process.exitCode = 1;
