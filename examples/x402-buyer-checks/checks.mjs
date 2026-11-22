#!/usr/bin/env node
// Two checks around an x402 payment, for any buyer agent. Node 18 or newer, no dependencies.
//
//   node checks.mjs preflight <url> [--method POST] [--body '{"text":"hola"}'] [--max-usd 0.01]
//   node checks.mjs settled <tx> <pay_to> <amount_usd> [--payer 0x…] [--nonce 0x…] [--network base]
//
// Both call free agents on the HESTIA hearth. This script signs nothing and pays nothing.
// Exit code: 0 when the verdict is the good one (looks_payable, paid), 2 otherwise, 1 on an error.

const HEARTH = process.env.HESTIA_URL || 'https://hestia.modelmarket.dev';

async function ask(slug, input) {
  const res = await fetch(`${HEARTH}/t/${slug}/invoke`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'user-agent': 'x402-buyer-checks/1' },
    body: JSON.stringify(input),
    signal: AbortSignal.timeout(60_000),
  });
  const text = await res.text();
  let answer;
  try { answer = JSON.parse(text); } catch { throw new Error(`${slug}: HTTP ${res.status}, not JSON`); }
  if (!res.ok || answer.ok === false || !answer.result) throw new Error(`${slug}: HTTP ${res.status} ${text.slice(0, 300)}`);
  return answer; // { ok, result, provider_pubkey, signature }: the answer is signed by the agent
}

/** Before paying: read the 402 unpaid and look the payee up on chain. Verdict `looks_payable` means go on. */
export async function preflight({ url, method = 'GET', body, maxUsd = '1.00' }) {
  const input = { url, method, max_usd: String(maxUsd), ...(body === undefined ? {} : { body }) };
  return (await ask('x402-preflight', input)).result;
}

/** After paying: did this transaction pay that payee exactly that amount, and is it final? Verdict `paid`. */
export async function settled({ tx, payTo, amountUsd, payer, nonce, network }) {
  const input = {
    tx, pay_to: payTo, amount_usd: String(amountUsd),
    ...(payer ? { payer } : {}), ...(nonce ? { nonce } : {}), ...(network ? { network } : {}),
  };
  return (await ask('x402-settlement', input)).result;
}

function flags(args) {
  const out = { _: [] };
  for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith('--')) out[args[i].slice(2)] = args[++i];
    else out._.push(args[i]);
  }
  return out;
}

function show(result) {
  console.log(`verdict: ${result.verdict}`);
  for (const c of result.checks || []) console.log(`  ${c.ok ? 'ok  ' : 'FAIL'} ${c.check}: ${c.detail}`);
}

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  const f = flags(rest);
  if (command === 'preflight' && f._.length === 1) {
    const r = await preflight({ url: f._[0], method: f.method, body: f.body ? JSON.parse(f.body) : undefined, maxUsd: f['max-usd'] });
    const offer = (r.offers || [])[0];
    if (offer) console.log(`offer:   $${offer.amount_usd} ${offer.asset_name || ''} on ${offer.network} to ${offer.pay_to}`);
    show(r);
    process.exit(r.verdict === 'looks_payable' ? 0 : 2);
  }
  if (command === 'settled' && f._.length === 3) {
    const r = await settled({ tx: f._[0], payTo: f._[1], amountUsd: f._[2], payer: f.payer, nonce: f.nonce, network: f.network });
    show(r);
    process.exit(r.verdict === 'paid' ? 0 : 2);
  }
  console.error('usage: checks.mjs preflight <url> [--method M] [--body JSON] [--max-usd N]\n'
    + '       checks.mjs settled <tx> <pay_to> <amount_usd> [--payer A] [--nonce N] [--network base]');
  process.exit(1);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => { console.error(String(err.message || err)); process.exit(1); });
}
