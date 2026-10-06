#!/usr/bin/env node
// Delivery survey: does an x402 seller deliver what it is paid for?
//
//   node survey.mjs catalog --out bazaar.json
//       every listing of the CDP Bazaar, as served today
//   node survey.mjs sample --catalog bazaar.json --hosts 100 --cap 0.01 --seed <text> --out plan.json
//       one listing for each of N sellers (a seller = a host), drawn by seeded hash, so anyone holding the
//       catalogue and the seed draws the same sample; ours and our sibling ecosystems' are never drawn.
//       --host your.host[,other.host]: a seller checking itself — every eligible listing of those hosts
//   node survey.mjs probe --plan plan.json --out probe.jsonl
//       the dry run: each seller's own declared example, sent exactly as a paid call would send it, minus
//       the payment; reads the 402 and says whether it could be paid within the cap and to the listed payee
//   node survey.mjs buy --plan plan.json --probe probe.jsonl --out buy.jsonl --budget 0.55 \
//       --payer 0x… --key-file ~/wallet.json [--address-index 1] [--limit N]
//       one paid call per seller the dry run found payable, only on the terms it saw then, never past the
//       budget; resumable (sellers already in --out are skipped and their payments count against the budget)
//   node survey.mjs chain --buy buy.jsonl --out chain.json [--rpc https://mainnet.base.org] [--pause-ms 400]
//       whether USDC executed each signed authorization: the buyer was charged, whatever the seller said
//   node survey.mjs tasks --buy buy.jsonl --catalog bazaar.json --out judge-in.jsonl
//       what the verifier is asked about each answer (judge_in_hub.py runs it inside the hub)
//   node survey.mjs report --plan plan.json --probe probe.jsonl --buy buy.jsonl --chain chain.json \
//       --judge judge-out.jsonl --out report
//       one row per drawn seller from every stage, the headline numbers (report.json) and a table (report.md)
//
// Only `buy` holds a key, and it reads it from a file it never prints. Requests go out over HTTPS, never
// through a redirect and never to a non-public address (lib.mjs).
import { appendFileSync, createWriteStream, existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { createPublicClient, http as rpc } from "viem";
import { mnemonicToAccount } from "viem/accounts";
import { base } from "viem/chains";
import {
  BINARY, PAYABLE, atomicToUsd, buildRequest, buyOne, chargedOnChain, classify, guardedRequest, outcome, payingClient, sample,
  usdToAtomic,
} from "./lib.mjs";

const BAZAAR = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources";
const PROBE_AGENT = "aimarket-delivery-survey/0.1 (+https://modelmarket.dev; dry run: reads the 402 terms once, pays nothing)";
const BUY_AGENT = "aimarket-delivery-survey/0.1 (+https://modelmarket.dev; buys one call per seller to check what is delivered)";

const readJsonl = (file) => (existsSync(file) ? readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []);
const expandHome = (p) => String(p).replace(/^~(?=\/)/, homedir());

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith("--")) continue;
    const key = argv[i].slice(2);
    const next = argv[i + 1];
    out[key] = next === undefined || next.startsWith("--") ? true : (i++, next);
  }
  return out;
}

function need(opts, ...keys) {
  for (const k of keys) if (opts[k] === undefined || opts[k] === true) throw new Error(`--${k} is required`);
}

async function catalog(opts) {
  need(opts, "out");
  const items = [];
  for (let offset = 0; ; ) {
    let page = null;
    for (let attempt = 0; attempt < 4 && !page; attempt++) {
      try {
        const res = await fetch(`${BAZAAR}?limit=1000&offset=${offset}`, { signal: AbortSignal.timeout(60_000) });
        if (res.ok) page = await res.json();
      } catch { /* retried below */ }
      if (!page) await new Promise((r) => setTimeout(r, 2_000 * (attempt + 1)));
    }
    if (!page) throw new Error(`the Bazaar did not answer at offset ${offset}`);
    const batch = Array.isArray(page.items) ? page.items : [];
    items.push(...batch);
    const total = page.pagination?.total;
    if (!batch.length || (total && items.length >= total)) break;
    offset += batch.length;
  }
  writeFileSync(opts.out, JSON.stringify(items));
  console.log(JSON.stringify({ saved: items.length, out: opts.out, at: new Date().toISOString() }));
}

function drawSample(opts) {
  need(opts, "catalog", "seed", "out");
  const items = JSON.parse(readFileSync(opts.catalog, "utf8"));
  const cap = usdToAtomic(opts.cap ?? "0.01");
  const hosts = Number.parseInt(opts.hosts ?? "100", 10);
  const only = typeof opts.host === "string" ? new Set(opts.host.toLowerCase().split(",").map((h) => h.trim()).filter(Boolean)) : null;
  const plan = sample(items, { hosts, cap, seed: String(opts.seed), only });
  plan.meta.catalogue_file = opts.catalog;
  plan.meta.drawn_at = new Date().toISOString();
  writeFileSync(opts.out, JSON.stringify(plan, null, 1));
  console.log(JSON.stringify(plan.meta, null, 1));
}

async function pool(items, size, work) {
  let next = 0;
  const run = async () => { while (next < items.length) { const i = next++; await work(items[i], i); } };
  await Promise.all(Array.from({ length: Math.min(size, items.length) }, run));
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor((s.length - 1) / 2)] : null;
};

async function probe(opts) {
  need(opts, "plan", "out");
  const plan = JSON.parse(readFileSync(opts.plan, "utf8"));
  const cap = BigInt(plan.meta.cap_atomic);
  const out = createWriteStream(opts.out);
  const rows = [];
  await pool(plan.entries, Number.parseInt(opts.concurrency ?? "8", 10), async (entry) => {
    const request = buildRequest(entry);
    const res = request.error ? {} : await guardedRequest(request, { userAgent: PROBE_AGENT });
    const row = {
      host: entry.host,
      resource: entry.resource,
      sent: request.error ? null : { method: request.method, url: request.url, body_bytes: request.body ? Buffer.byteLength(request.body) : 0 },
      declared_headers: request.declared_headers ?? [],
      status: res.status ?? null,
      ms: res.ms ?? null,
      listed: entry.listed,
      payers_30d: entry.quality?.l30DaysUniquePayers ?? null,
      ...classify(entry, request, res, cap),
    };
    delete row.offer;
    rows.push(row);
    out.write(`${JSON.stringify(row)}\n`);
  });
  out.end();

  const verdicts = {};
  for (const r of rows) verdicts[r.verdict] = (verdicts[r.verdict] || 0) + 1;
  const payable = rows.filter((r) => PAYABLE.has(r.verdict));
  const budget = payable.reduce((sum, r) => sum + BigInt(r.live.amount), 0n);
  const summary = {
    probed: rows.length,
    verdicts: Object.fromEntries(Object.entries(verdicts).sort((a, b) => b[1] - a[1])),
    payable: payable.length,
    budget_usdc: atomicToUsd(budget),
    price_usdc: { min: payable.length ? atomicToUsd(payable.map((r) => BigInt(r.live.amount)).reduce((a, b) => (a < b ? a : b))) : null,
      median: payable.length ? atomicToUsd(median(payable.map((r) => Number(r.live.amount)))) : null },
    median_ms: median(rows.filter((r) => r.ms !== null).map((r) => r.ms)),
    sellers_with_2plus_payers_30d: rows.filter((r) => (r.payers_30d ?? 0) >= 2).length,
    at: new Date().toISOString(),
  };
  writeFileSync(`${opts.out}.summary.json`, JSON.stringify(summary, null, 1));
  console.log(JSON.stringify(summary, null, 1));
}

async function buy(opts) {
  need(opts, "plan", "probe", "out", "budget", "payer", "key-file");
  const plan = JSON.parse(readFileSync(opts.plan, "utf8"));
  const cap = BigInt(plan.meta.cap_atomic);
  const entries = new Map(plan.entries.map((e) => [e.resource, e]));
  const approved = readJsonl(opts.probe).filter((r) => PAYABLE.has(r.verdict));
  const earlier = readJsonl(opts.out);
  const done = new Set(earlier.map((r) => r.host));
  let budgetLeft = usdToAtomic(opts.budget) - earlier.reduce((sum, r) => sum + (r.signed ? BigInt(r.signed.value) : 0n), 0n);

  const { mnemonic } = JSON.parse(readFileSync(expandHome(opts["key-file"]), "utf8"));
  const account = mnemonicToAccount(mnemonic, { addressIndex: Number.parseInt(opts["address-index"] ?? "1", 10) });
  if (account.address.toLowerCase() !== String(opts.payer).toLowerCase()) throw new Error("the key file does not hold the expected payer");
  const http = payingClient(account, `$${atomicToUsd(cap)}`);
  const send = (req, o) => guardedRequest(req, { userAgent: BUY_AGENT, ...o });

  let bought = 0;
  for (const row of approved) {
    if (done.has(row.host)) continue;
    if (opts.limit && bought >= Number.parseInt(opts.limit, 10)) break;
    if (budgetLeft <= 0n) break;
    const entry = entries.get(row.resource);
    let result;
    try {
      result = await buyOne(entry, row.live, { http, payer: account.address, cap, budgetLeft, send });
    } catch (e) {
      result = { stage: "quote", verdict: String(e?.message || e).slice(0, 120) };
    }
    if (result.signed) budgetLeft -= BigInt(result.signed.value);
    appendFileSync(opts.out, `${JSON.stringify({ host: entry.host, resource: entry.resource, approved: row.live, ...result, at: new Date().toISOString() })}\n`);
    console.log([entry.host, result.verdict, result.status ?? "-", `${result.ms ?? "-"}ms`, `left $${atomicToUsd(budgetLeft)}`].join("  "));
    bought++;
  }
  const rows = readJsonl(opts.out);
  const verdicts = {};
  for (const r of rows) verdicts[r.verdict] = (verdicts[r.verdict] || 0) + 1;
  console.log(JSON.stringify({ rows: rows.length, signed: rows.filter((r) => r.signed).length,
    signed_usdc: atomicToUsd(rows.reduce((s, r) => s + (r.signed ? BigInt(r.signed.value) : 0n), 0n)), verdicts }, null, 1));
}

async function chain(opts) {
  need(opts, "buy", "out");
  const client = createPublicClient({ chain: base, transport: rpc(opts.rpc ?? "https://mainnet.base.org") });
  const result = await chargedOnChain(readJsonl(opts.buy), (args) => client.readContract(args),
    { pauseMs: Number.parseInt(opts["pause-ms"] ?? "400", 10), backoffMs: 2_000 });
  writeFileSync(opts.out, JSON.stringify(result, null, 1));
  const sum = (xs) => atomicToUsd(xs.reduce((s, r) => s + BigInt(r.value), 0n));
  const now = Math.floor(Date.now() / 1000);
  console.log(JSON.stringify({
    signed: result.length,
    charged: result.filter((r) => r.charged === true).length, charged_usdc: sum(result.filter((r) => r.charged === true)),
    not_charged: result.filter((r) => r.charged === false).length,
    not_charged_but_still_settleable: result.filter((r) => r.charged === false && Number(r.valid_before) > now).length,
    unknown: result.filter((r) => r.charged === null).length,
  }, null, 1));
}

/** What the verifier is asked: the order (listing + the exact request) and the delivery, both as data. */
function tasks(opts) {
  need(opts, "buy", "catalog", "out");
  const catalogue = new Map(JSON.parse(readFileSync(opts.catalog, "utf8")).map((i) => [i.resource, i]));
  const lines = [];
  let binary = 0;
  for (const row of readJsonl(opts.buy)) {
    if (row.verdict !== "answered") continue;
    const type = String(row.response.content_type || "");
    if (BINARY.test(type)) { binary++; continue; }
    const listing = catalogue.get(row.resource) || {};
    const example = listing.extensions?.bazaar?.info?.output?.example;
    const text = Buffer.from(row.response.body_b64, "base64").toString("utf8");
    let body;
    try { body = JSON.parse(text); } catch { body = text.slice(0, 60_000); }
    const intent = [
      `A buyer paid ${atomicToUsd(row.signed.value)} USDC for one call to an x402 paid API (${row.resource}) and received the response below.`,
      `What the seller's listing promises: ${String(listing.description || "(no description)").slice(0, 2_000)}`,
      `The request the buyer sent, which is the seller's own example input from its listing: ${row.sent.method} ${row.sent.url}${row.sent.body ? ` with body ${row.sent.body.slice(0, 4_000)}` : ""}`,
      example === undefined ? "The listing gives no example of its output."
        : `The listing's example of its output (illustrative; real values may differ): ${JSON.stringify(example).slice(0, 4_000)}`,
      "The delivery fulfils the order if it is a genuine, complete answer to this request, of the kind the listing promises. It does not if it is an error message, an empty or placeholder result, a demand for further payment or credentials, or content unrelated to the request.",
    ].join("\n");
    const output = { http_status: row.status, content_type: type || null, body };
    lines.push(JSON.stringify({ id: row.host, intent, output_json: JSON.stringify(output) }));
  }
  writeFileSync(opts.out, lines.length ? `${lines.join("\n")}\n` : "");
  console.log(JSON.stringify({ tasks: lines.length, binary_not_judged: binary }));
}

function report(opts) {
  need(opts, "plan", "probe", "buy", "chain", "judge", "out");
  const plan = JSON.parse(readFileSync(opts.plan, "utf8"));
  const by = (rows, key = "host") => new Map(rows.map((r) => [r[key], r]));
  const probes = by(readJsonl(opts.probe));
  const buys = by(readJsonl(opts.buy));
  const chains = by(existsSync(opts.chain) ? JSON.parse(readFileSync(opts.chain, "utf8")) : []);
  const verdicts = by(readJsonl(opts.judge), "id");
  const rows = plan.entries.map((e) => {
    const b = buys.get(e.host);
    return {
      host: e.host, resource: e.resource, listed_usdc: atomicToUsd(e.listed.amount), payers_30d: e.quality?.l30DaysUniquePayers ?? null,
      paid_usdc: b?.signed ? atomicToUsd(b.signed.value) : null, status: b?.status ?? null, ms: b?.ms ?? null,
      content_type: b?.response?.content_type ?? null, bytes: b?.response?.bytes ?? null, tx: b?.settle?.transaction ?? null,
      ...outcome(probes.get(e.host), b, chains.get(e.host), verdicts.get(e.host)),
    };
  });
  const count = (f) => rows.filter(f).length;
  const usd = (f) => atomicToUsd(rows.filter(f).reduce((s, r) => s + usdToAtomic(r.paid_usdc ?? "0"), 0n));
  const outcomes = {};
  for (const r of rows) outcomes[r.outcome] = (outcomes[r.outcome] || 0) + 1;
  const summary = {
    seed: plan.meta.seed, catalogue: plan.meta.catalogue, eligible_hosts: plan.meta.eligible_hosts, drawn: rows.length,
    bought: count((r) => r.paid_usdc !== null), charged: count((r) => r.charged === true), charged_usdc: usd((r) => r.charged === true),
    outcomes,
    charged_without_a_delivery: count((r) => r.charged === true && r.outcome !== "delivered" && r.outcome !== "answered_not_judged"),
    usdc_spent_on_failed_or_missing: usd((r) => r.charged === true && ["failed_the_order", "charged_no_answer"].includes(r.outcome)),
    at: new Date().toISOString(),
  };
  writeFileSync(`${opts.out}.json`, JSON.stringify({ summary, rows }, null, 1));
  const cell = (v) => String(v ?? "").replace(/\|/g, "/").replace(/\s+/g, " ").slice(0, 140);
  const md = [
    "| seller | paid | payers 30d | outcome | score | charged | why |", "|---|---|---|---|---|---|---|",
    ...rows.map((r) => `| ${cell(r.host)} | ${cell(r.paid_usdc ?? "-")} | ${cell(r.payers_30d)} | ${cell(r.outcome)} | ${cell(r.score ?? "")} | ${cell(r.charged)} | ${cell(r.why)} |`),
  ].join("\n");
  writeFileSync(`${opts.out}.md`, `${md}\n`);
  console.log(JSON.stringify(summary, null, 1));
}

const [command, ...rest] = process.argv.slice(2);
const commands = { catalog, sample: drawSample, probe, buy, chain, tasks, report };
if (!commands[command]) {
  console.error("usage: survey.mjs catalog|sample|probe|buy|chain|tasks|report — see the header of this file");
  process.exit(2);
}
try {
  await commands[command](args(rest));
} catch (e) {
  console.error(String(e?.message || e));
  process.exit(1);
}
