// Offline check of the saved live 402s with our existing reference buyer.
// No key, signer, request or payment is created by this script.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { classify, usdToAtomic } from '../../scripts/delivery-survey/lib.mjs';

const rows = JSON.parse(readFileSync(new URL('./unpaid-probes.json', import.meta.url), 'utf8'));
const payee = '0x097f9685d1e0752bf8b02d61e5ce9be7ea0fba7f';
const checks = [];
for (const [key, amount] of [['route-check-unpaid', '50000'], ['recheck-unpaid', '5000']]) {
  const row = rows.find(r => r.key === key);
  const entry = { resource: row.url, listed: { amount, payTo: payee } };
  const request = { method: row.method, url: row.url, body: JSON.stringify(row.request) };
  const result = classify(entry, request, { status: row.status, headers: row.headers,
    body: Buffer.from(JSON.stringify(row.body)) }, usdToAtomic(amount === '50000' ? '0.05' : '0.005'));
  const accepted = result.verdict === 'payable' && result.x402_version === 2
    && result.live?.amount === amount && result.live?.payTo === payee;
  checks.push({ key, accepted, verdict: result.verdict, x402_version: result.x402_version,
    terms: result.live, source: 'unpaid-probes.json', proof_limit: 'The SDK can parse and accept these saved terms. No payment or paid response tested.' });
}
writeFileSync(new URL('./buyer-compatibility.json', import.meta.url), JSON.stringify({ checked_at_utc: new Date().toISOString(), checks }, null, 2) + '\n');
console.log(JSON.stringify(checks, null, 2));
if (checks.some(r => !r.accepted)) process.exitCode = 1;
