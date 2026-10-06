// The parts of the delivery survey that decide things: who is drawn, what is sent, how a 402 is read and
// which address a request may reach. survey.mjs only wires them to files and the network.
import { createHash } from "node:crypto";
import dns from "node:dns";
import https from "node:https";
import { BlockList, isIP } from "node:net";
import { x402Client, x402HTTPClient } from "@x402/core/client";
import { registerExactEvmScheme } from "@x402/evm/exact/client";
import { getAddress } from "viem";

export const USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913";
export const BASE_NETWORKS = new Set(["eip155:8453", "base"]);
// The EIP-712 domain of Base mainnet USDC. A seller that advertises another one can never be paid: the
// buyer signs for the advertised domain and the token contract rejects the signature.
export const USDC_BASE_DOMAIN = Object.freeze({ name: "USD Coin", version: "2" });

// Ours and our sibling ecosystems': never drawn, so the survey neither buys from itself nor lifts our rank.
export const OWN_HOST_SUFFIXES = ["modelmarket.dev", "independentai.network", "attestedmemory.net", "pingblip.com"];
export const OWN_WALLETS = new Set([
  "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",   // treasury
  "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",   // buyer
  "0x40409bE3bAf99f22aA86b2FBaAa99EF2188D5674",   // x402 settlement burner
  "0x9d24d267cf8d9a8b9ed104b4856cde8830c266ef",   // Independent's subcontract executor
  "0xB73d8Bc93B791510C4733C5C5Ac2015a3c2930Ec",   // Attested's payment wallet
  "0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D",   // AIMarketEscrow
].map((a) => a.toLowerCase()));

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/** "0.01" → 10000n: dollars to USDC's 6-decimal atomic units. */
export function usdToAtomic(usd) {
  const m = /^(\d{1,9})(?:\.(\d{1,6}))?$/.exec(String(usd).trim().replace(/^\$/, ""));
  if (!m) throw new Error(`not a dollar amount: ${usd}`);
  return BigInt(m[1]) * 1_000_000n + BigInt((m[2] || "").padEnd(6, "0"));
}

export const atomicToUsd = (a) => (Number(BigInt(a)) / 1e6).toFixed(6).replace(/0{1,4}$/, "");

function atomic(value) {
  if (typeof value === "string" && /^\d{1,30}$/.test(value)) return BigInt(value);
  if (Number.isSafeInteger(value) && value >= 0) return BigInt(value);
  return null;
}

/** The only offer this survey takes: exact scheme, Base mainnet USDC, a real payee, 0 < amount <= cap. */
export function usdcOffer(accepts, cap) {
  for (const a of Array.isArray(accepts) ? accepts : []) {
    if (!isObject(a) || a.scheme !== "exact" || !BASE_NETWORKS.has(a.network)) continue;
    if (String(a.asset || "").toLowerCase() !== USDC_BASE) continue;
    if (!/^0x[0-9a-fA-F]{40}$/.test(String(a.payTo || ""))) continue;
    const amount = atomic(a.amount ?? a.maxAmountRequired);
    if (amount === null || amount <= 0n || amount > cap) continue;
    return a;
  }
  return null;
}

/** What a buyer agrees to, in one comparable shape. */
export function terms(offer) {
  return {
    amount: String(atomic(offer.amount ?? offer.maxAmountRequired) ?? ""),
    payTo: String(offer.payTo || "").toLowerCase(),
    network: offer.network,
    asset: String(offer.asset || "").toLowerCase(),
    scheme: offer.scheme,
    domain: { name: offer.extra?.name ?? null, version: offer.extra?.version ?? null },
  };
}

export const ownHost = (host) => OWN_HOST_SUFFIXES.some((s) => host === s || host.endsWith(`.${s}`));

/** The request the seller itself declares as its example (Bazaar extension, x402 v2). */
export function declaredInput(item) {
  const input = item?.extensions?.bazaar?.info?.input;
  return isObject(input) ? input : null;
}

/** "ok", or why a listing cannot be drawn. */
export function eligibility(item, cap) {
  if (item?.x402Version !== 2) return "not_x402_v2";
  let url;
  try { url = new URL(item.resource); } catch { return "bad_url"; }
  if (url.protocol !== "https:") return "not_https";
  if (url.username || url.password) return "bad_url";
  const host = url.hostname.toLowerCase();
  if (isIP(host.replace(/^\[|\]$/g, ""))) return "ip_address_host";
  if (ownHost(host)) return "own_host";
  if (!declaredInput(item)) return "no_declared_input";
  const offer = usdcOffer(item.accepts, cap);
  if (!offer) return "no_base_usdc_offer_within_cap";
  if (OWN_WALLETS.has(String(offer.payTo).toLowerCase())) return "own_wallet";
  return "ok";
}

/** Seeded order: anyone with the catalogue and the seed draws the same sample. */
export const rank = (seed, key) => createHash("sha256").update(`${seed}\n${key}`).digest("hex");

/**
 * One listing for each of `hosts` sellers (a seller = a host), drawn by seeded hash from the eligible ones.
 * Every listing left out is counted under its reason, so the report can say what the sample does not cover.
 */
export function sample(items, { hosts, cap, seed, only = null }) {
  const reasons = {};
  const byHost = new Map();
  for (const item of items) {
    // A seller checking itself: only its own host, every eligible listing there instead of one.
    if (only && !only.has(hostOf(item.resource, "https://invalid.invalid") ?? "")) continue;
    const why = eligibility(item, cap);
    reasons[why] = (reasons[why] || 0) + 1;
    if (why !== "ok") continue;
    const host = new URL(item.resource).hostname.toLowerCase();
    if (!byHost.has(host)) byHost.set(host, []);
    byHost.get(host).push(item);
  }
  const drawn = [...byHost.keys()]
    .map((host) => [rank(seed, host), host])
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .slice(0, hosts)
    .map(([, host]) => host);
  const keyOf = (it) => `${it.resource}\n${declaredInput(it)?.method ?? ""}`;
  const pick = (host) => {
    const listings = byHost.get(host);
    return only ? listings : [listings.reduce((best, it) => (rank(seed, keyOf(it)) < rank(seed, keyOf(best)) ? it : best))];
  };
  const entries = drawn.flatMap((host) => pick(host).map((item) => {
    const listings = byHost.get(host);
    return {
      host,
      listings_at_host: listings.length,
      resource: item.resource,
      description: String(item.description || "").slice(0, 400),
      input: declaredInput(item),
      listed: terms(usdcOffer(item.accepts, cap)),
      quality: item.quality ?? null,
      last_updated: item.lastUpdated ?? null,
    };
  }));
  return {
    meta: { seed, cap_atomic: String(cap), catalogue: items.length, excluded: reasons, eligible_hosts: byHost.size, drawn: entries.length,
      ...(only ? { only_hosts: [...only] } : {}) },
    entries,
  };
}

// A parameter value that is a schema ({type, description}) rather than an example value: nothing to send.
const looksLikeSchema = (v) => isObject(v) && (typeof v.type === "string" || typeof v.description === "string");
const scalar = (v) => (isObject(v) || Array.isArray(v) ? JSON.stringify(v) : String(v));

/**
 * The seller's own example as an HTTP request: method, ":name" path parameters, query and body exactly as
 * declared. Declared headers are not sent (they are mostly the seller's own API keys); they are listed so a
 * failure can be read against them.
 */
export function buildRequest(entry) {
  const input = isObject(entry.input) ? entry.input : {};
  const method = String(input.method || (input.body !== undefined ? "POST" : "GET")).toUpperCase();
  if (!["GET", "POST", "PUT", "PATCH"].includes(method)) return { error: "method_not_supported" };
  let url;
  try { url = new URL(entry.resource); } catch { return { error: "bad_url" }; }

  const pathParams = isObject(input.pathParams) ? input.pathParams : {};
  if (Object.values(pathParams).some(looksLikeSchema)) return { error: "example_has_no_values" };
  const fill = (whole, name) => (name in pathParams ? `/${encodeURIComponent(scalar(pathParams[name]))}` : whole);
  const path = url.pathname.replace(/\/:([A-Za-z_]\w*)/g, fill).replace(/\/%7B([A-Za-z_]\w*)%7D/gi, fill);
  if (/\/:[A-Za-z_]|%7B[A-Za-z_]/i.test(path)) return { error: "path_parameter_without_example" };
  url.pathname = path;

  if (isObject(input.queryParams)) {
    if (Object.values(input.queryParams).some(looksLikeSchema)) return { error: "example_has_no_values" };
    for (const [k, v] of Object.entries(input.queryParams)) if (v !== undefined && v !== null) url.searchParams.set(k, scalar(v));
  }

  const headers = { accept: "application/json, */*;q=0.5" };
  let body = null;
  if (method !== "GET") {
    const type = String(input.bodyType || "json").toLowerCase();
    if (input.body === undefined) {
      body = "{}";
      headers["content-type"] = "application/json";
    } else if (type === "json") {
      body = JSON.stringify(input.body);
      headers["content-type"] = "application/json";
    } else if (type === "form-data" && isObject(input.body)) {
      body = new URLSearchParams(Object.entries(input.body).map(([k, v]) => [k, scalar(v)])).toString();
      headers["content-type"] = "application/x-www-form-urlencoded";
    } else if (type === "text" && typeof input.body === "string") {
      body = input.body;
      headers["content-type"] = "text/plain; charset=utf-8";
    } else {
      return { error: "body_type_not_supported" };
    }
    if (Buffer.byteLength(body) > 65_536) return { error: "example_too_large" };
  }
  return { method, url: url.toString(), headers, body, declared_headers: Object.keys(isObject(input.headers) ? input.headers : {}) };
}

// Everything that is not a public unicast address: loopback, private, shared, link-local, documentation,
// benchmarking, multicast, reserved, and the IPv6 forms that embed or translate IPv4 (mapped, NAT64, 6to4).
// Two lists, not one: a BlockList matches every IPv4 address against an IPv6 ::ffff:0:0/96 rule.
const NON_PUBLIC_V4 = new BlockList();
const NON_PUBLIC_V6 = new BlockList();
for (const [net, bits] of [["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10], ["127.0.0.0", 8], ["169.254.0.0", 16],
  ["172.16.0.0", 12], ["192.0.0.0", 24], ["192.0.2.0", 24], ["192.88.99.0", 24], ["192.168.0.0", 16], ["198.18.0.0", 15],
  ["198.51.100.0", 24], ["203.0.113.0", 24], ["224.0.0.0", 4], ["240.0.0.0", 4]]) NON_PUBLIC_V4.addSubnet(net, bits, "ipv4");
for (const [net, bits] of [["::", 96], ["::ffff:0:0", 96], ["64:ff9b::", 96], ["64:ff9b:1::", 48], ["100::", 64],
  ["2001::", 23], ["2001:db8::", 32], ["2002::", 16], ["fc00::", 7], ["fe80::", 10], ["fec0::", 10], ["ff00::", 8]]) NON_PUBLIC_V6.addSubnet(net, bits, "ipv6");

export function isPublicAddress(address) {
  const kind = isIP(address);
  if (kind === 4) return !NON_PUBLIC_V4.check(address, "ipv4");
  if (kind === 6) return !NON_PUBLIC_V6.check(address, "ipv6");
  return false;
}

/**
 * dns.lookup that refuses a host if ANY of its addresses is not public. The connection then uses the very
 * address checked here, so a rebinding answer between check and connect has nothing to slip through.
 */
export function publicLookup(hostname, options, callback) {
  if (typeof options === "function") { callback = options; options = {}; }
  dns.lookup(hostname, { all: true, family: options?.family || 0 }, (err, addresses) => {
    if (err) return callback(err);
    const list = Array.isArray(addresses) ? addresses : [];
    if (!list.length || list.some((a) => !isPublicAddress(a.address))) {
      return callback(Object.assign(new Error(`${hostname} resolves to a non-public address`), { code: "ENOTPUBLIC" }));
    }
    return options?.all ? callback(null, list) : callback(null, list[0].address, list[0].family);
  });
}

const ERRORS = { ENOTPUBLIC: "non_public_address", ETIMEDOUT: "timeout", ENOTFOUND: "dns_failed", EAI_AGAIN: "dns_failed",
  ECONNREFUSED: "connection_refused", ECONNRESET: "connection_reset", EHOSTUNREACH: "unreachable", ENETUNREACH: "unreachable" };

/**
 * One HTTPS request, never followed through a redirect, to a public address only, with a deadline and a cap on
 * the bytes read. Resolves (never rejects) to {status, headers, body, truncated, ms} or {error, ms}.
 */
export function guardedRequest(req, { userAgent, timeoutMs = 20_000, maxBytes = 262_144, lookup = publicLookup } = {}) {
  return new Promise((resolve) => {
    const started = performance.now();
    const ms = () => Math.round(performance.now() - started);
    let url;
    try { url = new URL(req.url); } catch { return resolve({ error: "bad_url", ms: 0 }); }
    if (url.protocol !== "https:") return resolve({ error: "not_https", ms: 0 });
    const literal = url.hostname.replace(/^\[|\]$/g, "");
    if (isIP(literal) && !isPublicAddress(literal)) return resolve({ error: "non_public_address", ms: 0 });

    let settled = false;
    let deadline = null;
    const done = (value) => { if (!settled) { settled = true; clearTimeout(deadline); resolve({ ...value, ms: ms() }); } };
    const headers = { ...req.headers, "user-agent": userAgent };
    if (req.body != null) headers["content-length"] = String(Buffer.byteLength(req.body));
    const r = https.request(url, { method: req.method, headers, lookup, agent: false }, (res) => {
      const chunks = [];
      let size = 0;
      let truncated = false;
      const finish = () => done({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks), truncated });
      res.on("data", (chunk) => {
        if (truncated) return;
        size += chunk.length;
        if (size > maxBytes) {
          truncated = true;
          chunks.push(chunk.subarray(0, chunk.length - (size - maxBytes)));
          res.destroy();
          finish();
        } else {
          chunks.push(chunk);
        }
      });
      res.on("end", finish);
      res.on("error", finish);
      res.on("close", finish);
    });
    deadline = setTimeout(() => r.destroy(Object.assign(new Error("deadline"), { code: "ETIMEDOUT" })), timeoutMs);
    r.on("error", (e) => {
      const code = String(e?.code || "");
      done({ error: ERRORS[code] || (/CERT|TLS|SSL/i.test(code) ? "tls_error" : "network_error"), detail: code || null });
    });
    if (req.body != null) r.write(req.body);
    r.end();
  });
}

const header = (res) => (name) => {
  const v = res.headers?.[name.toLowerCase()];
  return Array.isArray(v) ? v[0] : v;
};
const reader = new x402HTTPClient(new x402Client());

/** The 402's payment requirements, read the way the reference x402 client reads them (v2 header, v1 body). */
export function read402(res) {
  let body = null;
  try { body = JSON.parse(Buffer.from(res.body || "").toString("utf8")); } catch { body = null; }
  try {
    return { ok: true, required: reader.getPaymentRequiredResponse(header(res), body) };
  } catch {
    return { ok: false };
  }
}

/** Would this survey pay the live 402, and if not, why. Compared with what the Bazaar listed. */
export function judgeOffer(listed, required, cap) {
  const offers = (Array.isArray(required?.accepts) ? required.accepts : []).filter(
    (a) => isObject(a) && a.scheme === "exact" && BASE_NETWORKS.has(a.network) && String(a.asset || "").toLowerCase() === USDC_BASE);
  if (!offers.length) return { verdict: "no_base_usdc_offer" };
  const offer = usdcOffer(offers, cap);
  if (!offer) return { verdict: "over_cap", live: terms(offers[0]) };
  const live = terms(offer);
  if (live.payTo !== listed.payTo) return { verdict: "payee_changed", live };
  // The reference client will not sign without the token's domain, and USDC rejects a signature for another one.
  if (!live.domain.name || !live.domain.version) return { verdict: "no_usdc_domain", live };
  if (live.domain.name !== USDC_BASE_DOMAIN.name || String(live.domain.version) !== USDC_BASE_DOMAIN.version) {
    return { verdict: "wrong_usdc_domain", live };
  }
  return { verdict: live.amount === listed.amount ? "payable" : "payable_price_changed", live, offer };
}

export const PAYABLE = new Set(["payable", "payable_price_changed"]);

/** One dry-run row: what was sent, what came back, and whether a paid call could follow. */
export function classify(entry, request, res, cap) {
  if (request.error) return { verdict: request.error };
  if (res.error) return { verdict: res.error, detail: res.detail ?? null };
  const s = res.status;
  if (s === 402) {
    const read = read402(res);
    if (!read.ok) return { verdict: "unreadable_402" };
    return { x402_version: read.required?.x402Version ?? null, ...judgeOffer(entry.listed, read.required, cap) };
  }
  if (s >= 200 && s < 300) return { verdict: "open_without_payment" };
  if (s >= 300 && s < 400) return { verdict: "redirects", location_host: hostOf(res.headers?.location, entry.resource) };
  if (s === 400 || s === 422) return { verdict: "rejects_its_own_example" };
  if (s === 401 || s === 403) return { verdict: "needs_credentials" };
  if (s === 404 || s === 410) return { verdict: "gone" };
  if (s === 405) return { verdict: "method_not_allowed" };
  if (s === 429) return { verdict: "rate_limited" };
  if (s >= 500) return { verdict: "server_error" };
  return { verdict: `http_${s}` };
}

function hostOf(location, base) {
  try { return new URL(String(location), base).hostname; } catch { return null; }
}

// ── Buying ───────────────────────────────────────────────────────────────────────────────────────────

/**
 * The paying client: the exact scheme on Base mainnet only, the reference client's own spend cap set to the
 * survey's, no extensions registered (so it never signs a permit or an approval on a seller's say-so).
 */
export function payingClient(account, capUsd) {
  const client = new x402Client();
  registerExactEvmScheme(client, { signer: account, networks: ["eip155:8453"] });
  client.setSpendControls({ maxAmountPerPayment: capUsd });
  return new x402HTTPClient(client);
}

/** Two sets of terms (see `terms`) a buyer would treat as the same deal. */
export const sameTerms = (a, b) => Boolean(a && b) && a.amount === b.amount && a.payTo === b.payTo && a.asset === b.asset
  && a.network === b.network && a.scheme === b.scheme && a.domain?.name === b.domain?.name
  && String(a.domain?.version) === String(b.domain?.version);

/**
 * The signed payment must be one EIP-3009 transfer of exactly the approved amount, from the payer, to the approved
 * payee. Anything else — a permit, another payee, another amount — is refused before it leaves this process.
 */
export function checkPayload(payload, { payer, approved }) {
  const auth = payload?.payload?.authorization;
  const same = (x, y) => { try { return getAddress(String(x)) === getAddress(String(y)); } catch { return false; } };
  const ok = isObject(auth) && typeof payload.payload.signature === "string"
    && same(auth.from, payer) && same(auth.to, approved.payTo)
    && String(auth.value) === approved.amount && String(auth.validAfter) === "0"
    && /^\d{1,20}$/.test(String(auth.validBefore)) && /^0x[0-9a-fA-F]{64}$/.test(String(auth.nonce));
  if (!ok) throw new Error("payload_not_the_approved_transfer");
  return { from: getAddress(auth.from), to: getAddress(auth.to), value: String(auth.value), valid_before: String(auth.validBefore), nonce: auth.nonce };
}

/**
 * One purchase: the same request as the dry run, its 402 read again, paid only if the live terms are the approved
 * ones to the letter and fit the remaining budget. `send` is the transport (guardedRequest in production).
 * Returns the evidence row; `signed` is present exactly when an authorization was signed (it may settle later).
 */
export async function buyOne(entry, approved, { http, payer, cap, budgetLeft, send }) {
  const request = buildRequest(entry);
  if (request.error) return { stage: "quote", verdict: request.error };
  const quote = await send(request, {});
  if (quote.error) return { stage: "quote", verdict: quote.error };
  if (quote.status !== 402) return { stage: "quote", status: quote.status, ...classify(entry, request, quote, cap) };
  const read = read402(quote);
  if (!read.ok) return { stage: "quote", verdict: "unreadable_402" };
  const judged = judgeOffer(entry.listed, read.required, cap);
  if (!PAYABLE.has(judged.verdict)) return { stage: "quote", verdict: judged.verdict, live: judged.live ?? null };
  if (!sameTerms(judged.live, approved)) return { stage: "quote", verdict: "terms_changed_since_approval", live: judged.live };
  if ((judged.offer.extra?.assetTransferMethod ?? "eip3009") !== "eip3009") return { stage: "quote", verdict: "not_eip3009" };
  if (BigInt(approved.amount) > budgetLeft) return { stage: "quote", verdict: "over_budget" };

  let payload;
  try {
    payload = await http.createPaymentPayload({ ...read.required, accepts: [judged.offer] });
  } catch (e) {
    return { stage: "quote", verdict: "client_refused_offer", detail: String(e?.message || e).slice(0, 200) };
  }
  const signed = checkPayload(payload, { payer, approved });
  const paid = await send({ ...request, headers: { ...request.headers, ...http.encodePaymentSignatureHeader(payload) } },
    { timeoutMs: 90_000, maxBytes: 1_048_576 });
  const row = { stage: "paid", signed, x402_version: read.required.x402Version ?? null, sent: { method: request.method, url: request.url, body: request.body } };
  if (paid.error) return { ...row, verdict: "no_answer_after_payment", detail: paid.error, ms: paid.ms ?? null };

  let settle = null;
  try { settle = http.getPaymentSettleResponse(header(paid)); } catch { settle = null; }
  const body = Buffer.from(paid.body || "");
  Object.assign(row, {
    status: paid.status,
    ms: paid.ms,
    settle: settle && { success: settle.success ?? null, transaction: settle.transaction ?? null, network: settle.network ?? null,
      error: settle.errorReason ?? null },
    response: { content_type: header(paid)("content-type") ?? null, bytes: body.length, truncated: Boolean(paid.truncated),
      sha256: createHash("sha256").update(body).digest("hex"), body_b64: body.toString("base64") },
  });
  if (paid.status === 402) {
    const again = read402(paid);
    let reason = again.ok ? again.required?.error : null;
    if (!reason) { try { reason = JSON.parse(body.toString("utf8"))?.error; } catch { reason = null; } }
    return { ...row, verdict: "payment_refused", refusal: reason ? String(reason).slice(0, 300) : null };
  }
  if (paid.status >= 200 && paid.status < 300) return { ...row, verdict: body.length ? "answered" : "empty_answer" };
  return { ...row, verdict: "error_after_payment" };
}

// USDC (FiatTokenV2) marks every EIP-3009 nonce it has executed: the ground truth of "was the buyer charged".
export const AUTHORIZATION_STATE_ABI = [{
  type: "function", name: "authorizationState", stateMutability: "view",
  inputs: [{ name: "authorizer", type: "address" }, { name: "nonce", type: "bytes32" }],
  outputs: [{ name: "", type: "bool" }],
}];

/**
 * For each signed authorization, whether USDC executed it. `readContract` is viem's (or a stub in tests). Public RPCs
 * rate-limit a burst of reads, hence the pause between rows and the widening retries; still unknown → null.
 */
export async function chargedOnChain(rows, readContract, { pauseMs = 0, backoffMs = 1_000 } = {}) {
  const out = [];
  for (const row of rows) {
    if (!row.signed) continue;
    if (pauseMs) await new Promise((r) => setTimeout(r, pauseMs));
    let used = null;
    for (let attempt = 0; attempt < 4 && used === null; attempt++) {
      try {
        used = await readContract({ address: getAddress(USDC_BASE), abi: AUTHORIZATION_STATE_ABI, functionName: "authorizationState",
          args: [row.signed.from, row.signed.nonce] });
      } catch {
        await new Promise((r) => setTimeout(r, backoffMs * 2 ** attempt));
      }
    }
    out.push({ host: row.host, nonce: row.signed.nonce, value: row.signed.value, charged: used, valid_before: row.signed.valid_before,
      claimed_tx: row.settle?.transaction ?? null });
  }
  return out;
}

// ── Reporting ────────────────────────────────────────────────────────────────────────────────────────

// Answers the verifier cannot read as text: counted, not judged.
export const BINARY = /^(image|audio|video)\/|^application\/(pdf|zip|octet-stream)/i;

/** The outcome of one drawn seller, from the furthest stage it reached. */
export function outcome(p, b, c, j) {
  if (!b) return { outcome: "not_bought", why: p?.verdict ?? "not_probed" };
  if (!b.signed) return { outcome: "not_bought", why: b.verdict };
  const charged = c?.charged ?? null;
  if (b.verdict !== "answered") {
    const name = charged === true ? "charged_no_answer" : charged === false ? "not_charged_no_answer" : "charge_unknown_no_answer";
    return { outcome: name, why: b.verdict, charged };
  }
  if (!j) return { outcome: "answered_not_judged", why: BINARY.test(String(b.response?.content_type || "")) ? "binary" : "no_verdict", charged };
  if (j.kind !== "verdict" || !j.genuine) return { outcome: "answered_not_judged", why: j.cause || j.detail || j.kind, charged };
  return { outcome: j.passed ? "delivered" : "failed_the_order", why: (j.reasons || [])[0] ?? null, score: j.score, charged };
}

