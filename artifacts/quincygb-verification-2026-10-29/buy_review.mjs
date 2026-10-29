// Narrow, resumable review: exactly the three calls in paid-test-plan.json.
// User approved the deployer wallet and 0.06 USDC total on 2026-10-29.
import { readFileSync, writeFileSync, appendFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { payingClient, buyOne, guardedRequest, chargedOnChain, checkPayload, buildRequest } from '../../scripts/delivery-survey/lib.mjs';

const require = createRequire(new URL('../../scripts/delivery-survey/package.json', import.meta.url));
const { privateKeyToAccount } = require('viem/accounts');
const { createPublicClient, http, parseAbi } = require('viem');
const { base } = require('viem/chains');
const out = new URL('./', import.meta.url);
const plan = JSON.parse(readFileSync(new URL('paid-test-plan.json', out), 'utf8'));
const probes = JSON.parse(readFileSync(new URL('unpaid-probes.json', out), 'utf8'));
const maxTotal = 60000n;
const expectedPayer = '0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a';
const expectedPayee = '0x097f9685d1e0752bf8b02d61e5ce9be7ea0fba7f';
const allowed = [
  ['https://route-verdict-production.up.railway.app/v1/check', '50000'],
  ['https://stall-row-production.up.railway.app/v1/recheck', '5000'],
  ['https://stall-row-production.up.railway.app/v1/recheck', '5000'],
];
if (plan.calls.length !== 3 || plan.max_total_atomic !== '60000') throw Error('unexpected_plan');
for (let i = 0; i < 3; i++) {
  if (plan.calls[i].url !== allowed[i][0] || plan.calls[i].method !== 'POST'
      || plan.calls[i].max_amount_atomic !== allowed[i][1]) throw Error('unexpected_call');
  const target = plan.calls[i].body.resource_url ?? plan.calls[i].body.url;
  if (target !== 'https://modelmarket.dev/x402/histor-check') throw Error('unexpected_target');
}
if (plan.calls[1].body.watch_id !== plan.calls[2].body.watch_id) throw Error('watch_mismatch');
const entries = plan.calls.map(call => ({ resource: call.url,
  input: { type: 'http', method: 'POST', bodyType: 'json', body: call.body } }));
for (let i = 0; i < entries.length; i++) {
  const request = buildRequest(entries[i]);
  if (request.method !== 'POST' || request.url !== plan.calls[i].url
      || request.body !== JSON.stringify(plan.calls[i].body)) throw Error('request_builder_mismatch');
}
if (process.argv.includes('--validate-plan')) {
  console.log(JSON.stringify({ plan_valid: true, exact_POST_requests: 3, budget_atomic: '60000', key_loaded: false }));
  process.exit(0);
}

const secret = JSON.parse(readFileSync(`${homedir()}/.aicom-base-deployer-v4.json`, 'utf8'));
const account = privateKeyToAccount(secret.accounts[0].private_key);
if (account.address.toLowerCase() !== expectedPayer) throw Error('wrong_deployer_address');
for (const k of Object.keys(secret)) delete secret[k];
const rpc = createPublicClient({ chain: base, transport: http('https://mainnet.base.org', { timeout: 20000, retryCount: 1 }) });
if (await rpc.getChainId() !== 8453) throw Error('wrong_rpc_chain');
const balance = await rpc.readContract({ address: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', abi: parseAbi(['function balanceOf(address) view returns (uint256)']), functionName: 'balanceOf', args: [account.address] });
const preflight = { at_utc: new Date().toISOString(), payer: account.address, expected_payee: expectedPayee,
  balance_sufficient: balance >= maxTotal, budget_usdc: '0.06', authorized_calls: 3, signed: false };
writeFileSync(new URL('payer-preflight.json', out), JSON.stringify(preflight, null, 2) + '\n');
console.log(JSON.stringify({ stage: 'preflight', ...preflight }));
if (balance < maxTotal) throw Error('insufficient_usdc_for_approved_plan');
if (!process.argv.includes('--execute')) process.exit(0);

const journal = new URL('payment-authorizations.jsonl', out);
const resultFile = new URL('paid-results.jsonl', out);
const readLines = f => existsSync(f) ? readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : [];
const records = readLines(resultFile);
const previousAuthorizations = readLines(journal);
let budgetLeft = maxTotal - previousAuthorizations.reduce((s, r) => s + BigInt(r.signed.value), 0n);
if (budgetLeft < 0n) throw Error('journal_over_budget');
const signedIds = new Set(previousAuthorizations.map(r => r.call_id));
const completedIds = new Set(records.map(r => r.call_id));
for (const callId of signedIds) if (!completedIds.has(callId)) throw Error('unresolved_prior_authorization_do_not_retry');

for (let i = 0; i < 3; i++) {
  const callId = `review-${i + 1}`;
  if (completedIds.has(callId)) continue;
  const call = plan.calls[i];
  const approvedProbe = probes.find(r => r.key === (i === 0 ? 'route-check-unpaid' : 'recheck-unpaid'));
  const offer = approvedProbe.payment_required_decoded.accepts[0];
  const approved = { amount: allowed[i][1], payTo: expectedPayee, network: 'eip155:8453',
    asset: '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', scheme: 'exact', domain: { name: 'USD Coin', version: '2' } };
  if (offer.amount !== approved.amount || offer.payTo.toLowerCase() !== approved.payTo) throw Error('probe_terms_mismatch');
  const entry = { ...entries[i], listed: approved };
  const client = payingClient(account, i === 0 ? '$0.05' : '$0.005');
  let persisted = false;
  const send = async (request, options) => {
    if (request.method !== 'POST' || request.url !== call.url
        || request.body !== JSON.stringify(call.body)) throw Error('refuse_unapproved_request');
    const signatureHeader = Object.entries(request.headers).find(([k]) => k.toLowerCase() === 'payment-signature');
    if (signatureHeader) {
      if (persisted) throw Error('only_one_signed_request_per_call');
      const payload = JSON.parse(Buffer.from(signatureHeader[1], 'base64').toString('utf8'));
      const signed = checkPayload(payload, { payer: account.address, approved });
      if (BigInt(signed.value) > budgetLeft) throw Error('budget_exceeded_before_send');
      // Store only public authorization fields, NEVER the private key or signature.
      appendFileSync(journal, JSON.stringify({ call_id: callId, at_utc: new Date().toISOString(), signed }) + '\n');
      budgetLeft -= BigInt(signed.value);
      persisted = true;
    }
    return guardedRequest(request, { ...options, userAgent: 'aimarket-independent-review/0.1 (+https://modelmarket.dev; user-requested purchase)' });
  };
  const result = await buyOne(entry, approved, { http: client, payer: account.address,
    cap: BigInt(approved.amount), budgetLeft, send });
  const record = { call_id: callId, at_utc: new Date().toISOString(), host: new URL(call.url).hostname, resource: call.url, ...result };
  if (record.response?.body_b64) {
    const raw = Buffer.from(record.response.body_b64, 'base64');
    writeFileSync(new URL(`${callId}-response.body`, out), raw);
    record.response.sha256 = createHash('sha256').update(raw).digest('hex');
  }
  appendFileSync(resultFile, JSON.stringify(record) + '\n');
  records.push(record);
  console.log(JSON.stringify({ call_id: callId, verdict: result.verdict, status: result.status, signed_units: result.signed?.value ?? '0', settlement: result.settle, budget_remaining_atomic: String(budgetLeft) }));
  if (result.verdict !== 'answered') break;
}
const chain = await chargedOnChain(records, args => rpc.readContract(args), { pauseMs: 400 });
writeFileSync(new URL('chain-verification.json', out), JSON.stringify(chain, null, 2) + '\n');
console.log(JSON.stringify({ stage: 'chain', records: chain }));
