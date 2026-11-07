#!/usr/bin/env node
// Supplier review — the deterministic half of the Multica agent «ревьюер поставщиков».
//
// Reads what modelmarket.dev publishes about its sellers (the signed manifest, the federation peers
// and the observed x402 sellers), compares it with the state of the previous run and checks every
// new or changed listing for broken schemas, prompt injection (WARDEN's static scan) and the
// permissions a buyer would hand over. It opens no socket and runs nothing it reads: the caller
// downloads the three documents (run.sh does it with curl, through the agent's egress proxy).
//
//   node review.mjs --manifest m.json --peers p.json --observed o.json --state state.json \
//                   --out report.json --md report.md [--warden DIR] [--now ISO]
//
// The model that writes the human report reads report.json. Listing text is the attack surface,
// so every fact a buyer needs (findings, counts, severities) is decided here, in code, and the
// Markdown facts block is written here too: an injected description can make the model's prose
// wrong, not the facts under it.
//
// The report never recommends hiding or rejecting a seller. It states what was found and what the
// author could fix; deciding anything else is the operator's job.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const STATE_VERSION = 1;
export const MAX_TEXT = 2000;
const MAX_ITEMS_MD = 60;

/** Hosts run by this ecosystem. A seller elsewhere is "outside" and gets a welcome draft. */
export const OUR_DOMAINS = ['modelmarket.dev', 'attestedmemory.net', 'independentai.network', 'magic-ai-factory.com'];

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2, info: 3 };

// ── small helpers ──────────────────────────────────────────────────────────────────────────

export function hostOf(url) {
  try {
    return new URL(String(url)).hostname.toLowerCase();
  } catch {
    return '';
  }
}

/**
 * Why an outside source gets no welcome letter, or null when it can get one. An author's address is https under a
 * public name; anything else (http, a bare IP, a name without a dot, a user name in the address) is no one to
 * write to. On 2026-11-06 sixty-nine such pending peers were announced in under four hours, probes of the hub's
 * address checks (rebinding names, 127.0.0.1@host, redirects to 169.254.169.254, internal ports).
 */
export function noWelcomeReason(source) {
  let u;
  try {
    u = new URL(String(source));
  } catch {
    return 'no_public_name';
  }
  if (u.protocol !== 'https:') return 'not_https';
  if (u.username || u.password) return 'credentials_in_address';
  const h = u.hostname;
  if (!h.includes('.') || h.startsWith('[') || /^\d{1,3}(?:\.\d{1,3}){3}$/.test(h)) return 'no_public_name';
  return null;
}

export function isOurs(url) {
  const host = hostOf(url);
  // A bare container name (no dot) is reachable only inside the hub's own host.
  return Boolean(host) && (!host.includes('.') || OUR_DOMAINS.some((d) => host === d || host.endsWith('.' + d)));
}

function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map((k) => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  return JSON.stringify(value ?? null);
}

export function fingerprint(value) {
  return createHash('sha256').update(canonical(value)).digest('hex').slice(0, 24);
}

function clip(text, max = MAX_TEXT) {
  const s = typeof text === 'string' ? text : '';
  return s.length > max ? s.slice(0, max) + ` …[+${s.length - max} chars]` : s;
}

function finding(check, code, severity, where, detail) {
  return { check, code, severity, where, detail };
}

// ── schemas ────────────────────────────────────────────────────────────────────────────────

const TYPES = new Set(['string', 'number', 'integer', 'boolean', 'object', 'array', 'null']);
const TYPED = ['type', 'enum', 'const', '$ref', 'anyOf', 'oneOf', 'allOf', 'not', 'properties', 'items'];

function pointer(root, ref) {
  if (ref === '#') return root;
  if (!ref.startsWith('#/')) return undefined;
  let node = root;
  for (const raw of ref.slice(2).split('/')) {
    const key = decodeURIComponent(raw).replace(/~1/g, '/').replace(/~0/g, '~');
    if (!node || typeof node !== 'object' || !(key in node)) return undefined;
    node = node[key];
  }
  return node;
}

function typeMatches(value, types) {
  return types.some((t) =>
    (t === 'null' && value === null) ||
    (t === 'array' && Array.isArray(value)) ||
    (t === 'object' && value !== null && typeof value === 'object' && !Array.isArray(value)) ||
    (t === 'integer' && Number.isInteger(value)) ||
    (t === 'number' && typeof value === 'number') ||
    (t === 'string' && typeof value === 'string') ||
    (t === 'boolean' && typeof value === 'boolean'));
}

/** Problems a strict buyer (or a model filling the form) would hit. Not a full meta-schema check. */
export function schemaProblems(schema, where, { input = false } = {}) {
  const out = [];
  if (schema === undefined || schema === null) {
    if (input) out.push(finding('schema', 'no_input_schema', 'medium', where, 'no input schema: a buyer cannot tell what to send'));
    return out;
  }
  if (typeof schema !== 'object' || Array.isArray(schema)) {
    out.push(finding('schema', 'schema_not_object', 'medium', where, 'the schema is not a JSON object'));
    return out;
  }
  if (input && schema.type !== undefined && schema.type !== 'object') {
    out.push(finding('schema', 'input_not_object', 'medium', where, `input schema type is ${JSON.stringify(schema.type)}; MCP tools take an object`));
  }
  const untyped = [];
  const walk = (node, path, depth) => {
    if (depth > 12 || node === true || node === false) return;
    if (!node || typeof node !== 'object' || Array.isArray(node)) {
      out.push(finding('schema', 'subschema_not_object', 'medium', path, 'a sub-schema is not an object'));
      return;
    }
    if (node.type !== undefined) {
      const types = Array.isArray(node.type) ? node.type : [node.type];
      const bad = types.filter((t) => !TYPES.has(t));
      if (bad.length) out.push(finding('schema', 'unknown_type', 'medium', path, `unknown type ${JSON.stringify(bad)}`));
      if (node.default !== undefined && !bad.length && !typeMatches(node.default, types)) {
        out.push(finding('schema', 'default_type_mismatch', 'low', path, `default ${clip(JSON.stringify(node.default), 80)} is not ${types.join('|')}`));
      }
    }
    if (node.enum !== undefined) {
      if (!Array.isArray(node.enum) || node.enum.length === 0) out.push(finding('schema', 'empty_enum', 'medium', path, 'enum is empty: no value is valid'));
      else if (node.default !== undefined && !node.enum.some((v) => canonical(v) === canonical(node.default))) {
        out.push(finding('schema', 'default_not_in_enum', 'low', path, 'default is not one of the enum values'));
      }
    }
    if (typeof node.pattern === 'string') {
      try {
        new RegExp(node.pattern, 'u');
      } catch {
        try {
          new RegExp(node.pattern);
        } catch {
          out.push(finding('schema', 'bad_pattern', 'medium', path, `pattern ${clip(JSON.stringify(node.pattern), 80)} is not a valid regular expression`));
        }
      }
    }
    for (const [lo, hi] of [['minimum', 'maximum'], ['exclusiveMinimum', 'exclusiveMaximum'], ['minLength', 'maxLength'], ['minItems', 'maxItems'], ['minProperties', 'maxProperties']]) {
      if (typeof node[lo] === 'number' && typeof node[hi] === 'number' && node[lo] > node[hi]) {
        out.push(finding('schema', 'impossible_range', 'medium', path, `${lo} ${node[lo]} > ${hi} ${node[hi]}: no value is valid`));
      }
    }
    if (typeof node.$ref === 'string') {
      if (node.$ref.startsWith('#')) {
        if (pointer(schema, node.$ref) === undefined) out.push(finding('schema', 'dangling_ref', 'medium', path, `$ref ${clip(node.$ref, 80)} points nowhere`));
      } else {
        out.push(finding('schema', 'remote_ref', 'low', path, `$ref ${clip(node.$ref, 120)} points outside the schema; a validator would have to fetch it`));
      }
    }
    if (node.required !== undefined) {
      if (!Array.isArray(node.required) || node.required.some((r) => typeof r !== 'string')) {
        out.push(finding('schema', 'bad_required', 'medium', path, '`required` is not a list of names'));
      } else if (node.properties && typeof node.properties === 'object') {
        const missing = node.required.filter((r) => !(r in node.properties));
        if (missing.length) out.push(finding('schema', 'required_not_in_properties', 'medium', path, `required ${JSON.stringify(missing)} not described in properties`));
      }
    }
    if (node.properties !== undefined) {
      if (!node.properties || typeof node.properties !== 'object' || Array.isArray(node.properties)) {
        out.push(finding('schema', 'bad_properties', 'medium', path, '`properties` is not an object'));
      } else {
        for (const [name, sub] of Object.entries(node.properties)) {
          if (sub && typeof sub === 'object' && !Array.isArray(sub) && !TYPED.some((k) => k in sub)) untyped.push(path === where ? name : `${path.slice(where.length + 1)}.${name}`);
          walk(sub, `${path}.${name}`, depth + 1);
        }
      }
    }
    if (node.items !== undefined) {
      if (Array.isArray(node.items)) node.items.forEach((s, i) => walk(s, `${path}[${i}]`, depth + 1));
      else walk(node.items, `${path}[]`, depth + 1);
    }
    for (const key of ['anyOf', 'oneOf', 'allOf']) {
      if (Array.isArray(node[key])) node[key].forEach((s, i) => walk(s, `${path}.${key}[${i}]`, depth + 1));
    }
    for (const key of ['$defs', 'definitions']) {
      if (node[key] && typeof node[key] === 'object') for (const [n, s] of Object.entries(node[key])) walk(s, `${path}.${key}.${n}`, depth + 1);
    }
  };
  walk(schema, where, 0);
  if (untyped.length) out.push(finding('schema', 'untyped_properties', 'low', where, `no type for ${JSON.stringify(untyped.slice(0, 12))}${untyped.length > 12 ? ` and ${untyped.length - 12} more` : ''}`));
  return out;
}

// ── what a buyer hands over ───────────────────────────────────────────────────────────────

// A credential for something else: the buyer would be handing over its own key. A plain `seed` is a random seed
// (oracles, generators), not a wallet's, so only the wallet spellings count.
const SECRET_FIELD = /^(?:.*[_-])?(?:api[_-]?key|apikey|secret|client[_-]?secret|password|passwd|passphrase|private[_-]?key|privkey|secret[_-]?key|seed[_-]?phrase|wallet[_-]?seed|mnemonic|ssh[_-]?key|credentials?|cookie|(?:github|gitlab|openai|anthropic|slack|discord|telegram|stripe|aws|gcp|azure)[_-]?(?:token|key|secret))(?:[_-].*)?$/i;
// A token may be one this seller issued (a game session, a preflight ticket) — normal — or the buyer's own login
// somewhere else. The schema cannot tell, so it is a question for the author, not an accusation.
const TOKEN_FIELD = /^(?:.*[_-])?(?:access|auth|refresh|bearer|session|id)[_-]?token$|^(?:token|bearer)$/i;
const SECRET_TEXT = /\b(?:your|the user'?s|buyer'?s)\s+(?:api[\s-]?key|password|private[\s-]?key|seed[\s-]?phrase|mnemonic|access[\s-]?token|secret[\s-]?key|credentials?)\b/i;
const URL_FIELD = /^(?:url|uri|link|endpoint|webhook(?:_url)?|callback(?:_url)?|target(?:_url)?|redirect(?:_uri|_url)?|.*_url)$/i;
const CODE_FIELD = /^(?:code|script|command|cmd|shell|sql|expression|eval|source_code|program)$/i;
const PATH_FIELD = /^(?:path|file|file_?path|filename|dir|directory|folder)$/i;
const PERSONAL_FIELD = /^(?:email|e_?mail|phone|phone_?number|mobile|address|street|full_?name|first_?name|last_?name|passport(?:_number)?|ssn|date_of_birth|dob|birth_?date|iban|card_?number|cvv|tax_?id)$/i;
const MONEY_TEXT = /\b(?:transfer|withdraw|payout|send (?:funds|money|tokens|usdc|eth|btc)|swap|bridge|approve (?:spending|an allowance|allowance)|sign (?:a |the )?transaction|place (?:an |a )?(?:order|bet)|stake|purchase|buy)\b/i;

function fields(schema, path = '', out = [], depth = 0) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema) || depth > 8) return out;
  if (schema.properties && typeof schema.properties === 'object' && !Array.isArray(schema.properties)) {
    for (const [name, sub] of Object.entries(schema.properties)) {
      const at = path ? `${path}.${name}` : name;
      out.push({ name, at, schema: sub && typeof sub === 'object' ? sub : {} });
      fields(sub, at, out, depth + 1);
    }
  }
  if (schema.items && typeof schema.items === 'object' && !Array.isArray(schema.items)) fields(schema.items, `${path}[]`, out, depth + 1);
  return out;
}

export function permissionSignals(tool) {
  const out = [];
  const all = fields(tool.input_schema);
  const pick = (re) => all.filter((f) => re.test(f.name)).map((f) => f.at);
  const secret = all.filter((f) => SECRET_FIELD.test(f.name) || SECRET_TEXT.test(String(f.schema.description ?? ''))).map((f) => f.at);
  if (secret.length || SECRET_TEXT.test(String(tool.description ?? ''))) {
    out.push(finding('permissions', 'asks_for_secret', 'high', 'input', secret.length
      ? `asks the buyer for a credential in ${JSON.stringify(secret)}`
      : 'the description asks the buyer for a credential'));
  }
  const tokens = all.filter((f) => TOKEN_FIELD.test(f.name) && !secret.includes(f.at)).map((f) => f.at);
  if (tokens.length) {
    out.push(finding('permissions', 'takes_token', 'low', 'input', `takes a token in ${JSON.stringify(tokens)}: fine if this seller issued it, a risk if buyers are meant to pass their own login for another service — the schema should say which`));
  }
  const personal = pick(PERSONAL_FIELD);
  if (personal.length) out.push(finding('permissions', 'personal_data', 'info', 'input', `collects personal data: ${JSON.stringify(personal)}`));
  const urls = all.filter((f) => URL_FIELD.test(f.name) || f.schema.format === 'uri' || f.schema.format === 'url').map((f) => f.at);
  if (urls.length) out.push(finding('permissions', 'calls_buyer_url', 'info', 'input', `the seller fetches or calls an address the buyer gives: ${JSON.stringify(urls)}`));
  const code = pick(CODE_FIELD);
  if (code.length) out.push(finding('permissions', 'runs_buyer_code', 'info', 'input', `takes code or a command: ${JSON.stringify(code)}`));
  const paths = pick(PATH_FIELD);
  if (paths.length) out.push(finding('permissions', 'file_path_input', 'info', 'input', `takes a file path: ${JSON.stringify(paths)}`));
  const text = `${tool.name ?? ''} ${tool.display_name ?? ''} ${tool.description ?? ''}`;
  const money = MONEY_TEXT.exec(text);
  if (money) out.push(finding('permissions', 'has_effects', 'info', 'description', `the call has effects outside the answer (“${money[0]}”): a buyer agent should confirm before calling`));
  return out;
}

// ── address and price ─────────────────────────────────────────────────────────────────────

export function endpointProblems(tool) {
  const out = [];
  const local = (tool.source_hub ?? 'local') === 'local';
  const url = tool.invoke_url;
  if (!url) {
    if (local) out.push(finding('endpoint', 'no_invoke_url', 'medium', 'invoke_url', 'no address to call'));
  } else {
    let parsed = null;
    try {
      parsed = new URL(url);
    } catch {
      out.push(finding('endpoint', 'bad_invoke_url', 'medium', 'invoke_url', 'the address does not parse'));
    }
    if (parsed) {
      if (parsed.protocol !== 'https:') out.push(finding('endpoint', 'not_https', 'high', 'invoke_url', `${parsed.protocol} — calls and answers travel unencrypted`));
      if (parsed.username || parsed.password) out.push(finding('endpoint', 'credentials_in_url', 'high', 'invoke_url', 'the address carries a user name or password'));
      if (/^\[|^\d{1,3}(?:\.\d{1,3}){3}$/.test(parsed.hostname)) out.push(finding('endpoint', 'ip_address_host', 'low', 'invoke_url', 'the address is a bare IP, not a name'));
      if (!parsed.hostname.includes('.') && !parsed.hostname.startsWith('[')) {
        out.push(finding('endpoint', 'internal_address', 'medium', 'invoke_url', `\u201c${parsed.hostname}\u201d is a name inside the seller's own network: nobody outside can call it`));
      }
    }
  }
  const price = tool.price_per_call_usd;
  if (typeof price !== 'number' || !Number.isFinite(price) || price < 0) {
    out.push(finding('price', 'bad_price', 'medium', 'price_per_call_usd', `price ${JSON.stringify(price)} is not a number ≥ 0`));
  } else {
    if (price > 1) out.push(finding('price', 'high_price', 'low', 'price_per_call_usd', `$${price} a call`));
    const routed = tool.routed_price_usd;
    const bps = Number(tool.routing_fee_bps ?? 0);
    if (typeof routed === 'number' && (routed + 1e-9 < price || routed > price * (1 + bps / 10_000) + 1e-6)) {
      out.push(finding('price', 'routed_price_mismatch', 'medium', 'routed_price_usd', `routed $${routed} vs listed $${price} with ${bps} bps routing fee`));
    }
  }
  if (local && !tool.provider_pubkey) out.push(finding('endpoint', 'no_provider_key', 'low', 'provider_pubkey', 'no seller key: buyers cannot check this seller’s own receipts'));
  if (tool.route_status && tool.route_status !== 'live') out.push(finding('endpoint', 'route_not_live', 'low', 'route_status', `route is ${tool.route_status}`));
  const desc = typeof tool.description === 'string' ? tool.description.trim() : '';
  if (desc.length < 30) out.push(finding('description', 'thin_description', 'low', 'description', `${desc.length} characters: too little for a buyer agent to choose this tool`));
  return out;
}

// ── WARDEN ─────────────────────────────────────────────────────────────────────────────────

export async function loadWarden(dir) {
  const base = resolve(dir ?? process.env.WARDEN_PACKAGE ?? join(homedir(), 'tools', 'warden'));
  const mod = await import(pathToFileURL(join(base, 'dist', 'index.js')).href);
  const pkg = JSON.parse(readFileSync(join(base, 'package.json'), 'utf8'));
  const feed = new mod.ThreatFeed({}); // built-in floor only, never load()ed: no network
  return {
    version: pkg.version,
    ruleset: mod.staticScanRuleset().version,
    staticScan: new mod.StaticScanGate(),
    threat: new mod.ThreatGate(feed),
  };
}

const POLICY = { blockAtSeverity: 'high', sensitiveToolPatterns: [], allowUnknownServers: true, pinToolDefs: false };

function wardenSeverity(f) {
  // An advisory match is a word, not a finding: "instead of", "API key", "secrets". WARDEN rates some of them info
  // ("instead of"), and that rating stays; none rises above low.
  if (f.advisory) return f.severity === 'info' ? 'info' : 'low';
  return f.severity === 'critical' || f.severity === 'high' ? 'high' : 'medium';
}

/** WARDEN's static scan over the text a buyer's model would read, and its deny list over the seller's identity. */
export async function wardenFindings(warden, tool, server) {
  const def = {
    name: String(tool.name ?? ''),
    description: typeof tool.description === 'string' ? tool.description : '',
    inputSchema: tool.input_schema && typeof tool.input_schema === 'object' ? tool.input_schema : {},
    ...(tool.output_schema && typeof tool.output_schema === 'object' && !Array.isArray(tool.output_schema) ? { outputSchema: tool.output_schema } : {}),
  };
  const ref = { id: String(server.id ?? ''), name: String(server.name ?? server.id ?? ''), transport: 'http', url: String(server.url ?? '') };
  const scanned = await warden.staticScan.evaluate({ server: ref, tools: [def], prior: [], policy: POLICY });
  const listed = await warden.threat.evaluate({ server: ref, tools: [], prior: [], policy: POLICY });
  return [...scanned.findings, ...listed.findings].map((f) => ({
    ...finding('injection', f.code, wardenSeverity(f), f.gate === 'static-scan' ? 'text' : 'seller identity', clip(f.message, 400)),
    ...(f.advisory ? { advisory: true } : {}),
  }));
}

/**
 * What a welcome letter may raise with the author: real problems (high or medium) and schema defects, never an
 * advisory WARDEN match. Those matches are weak signals for the owner's report. Asking an author to reword around
 * them teaches evasion and can make a good description worse: textokit's "remove secrets and personal data before
 * submitting" matched the credential pattern (2026-11-04 drafts).
 */
export function letterPoints(findings) {
  return findings.filter((f) => !f.advisory && f.severity !== 'info'
    && (f.severity === 'high' || f.severity === 'medium' || f.check === 'schema'));
}

// ── the run ────────────────────────────────────────────────────────────────────────────────

function listingKey(t) {
  return `${t.source_hub || 'local'}|${t.product_id}|${t.capability_id}`;
}

function listingView(t) {
  return {
    name: t.name, description: t.description, input_schema: t.input_schema, output_schema: t.output_schema,
    price_per_call_usd: t.price_per_call_usd, invoke_url: t.invoke_url, access_mode: t.access_mode,
  };
}

function sourceOf(t, hubUrl) {
  return (t.source_hub && t.source_hub !== 'local') ? t.source_hub : (t.invoke_url || hubUrl);
}

function changedFields(before, after) {
  return Object.keys(after).filter((k) => canonical(before?.[k]) !== canonical(after[k]));
}

function worst(findings) {
  return findings.reduce((w, f) => (SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[w] ? f.severity : w), 'info');
}

function sortFindings(list) {
  return list.sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] || a.check.localeCompare(b.check));
}

export async function review({ manifest, peers, observed, state, now, warden }) {
  const at = now ?? new Date().toISOString();
  const baseline = !state || state.version !== STATE_VERSION;
  const prev = baseline ? { listings: {}, peers: {}, routes: {} } : state;
  const next = { version: STATE_VERSION, baselineAt: baseline ? at : state.baselineAt, lastRunAt: at, listings: {}, peers: {}, routes: {} };
  const hubUrl = manifest.base_url || 'https://modelmarket.dev';
  const items = [];
  const counts = { listings: 0, new: 0, changed: 0, removed: 0, peersNew: 0, peersChanged: 0, routesNew: 0, routesChanged: 0 };

  for (const t of manifest.tools ?? []) {
    counts.listings += 1;
    const key = listingKey(t);
    const view = listingView(t);
    const fp = fingerprint(view);
    const was = prev.listings[key];
    next.listings[key] = { fp, view: fingerprintedView(view), firstSeen: was?.firstSeen ?? at };
    const status = baseline ? 'baseline' : !was ? 'new' : was.fp !== fp ? 'changed' : null;
    if (status === 'new') counts.new += 1;
    if (status === 'changed') counts.changed += 1;
    if (!status) continue;
    const source = sourceOf(t, hubUrl);
    const findings = sortFindings([
      ...schemaProblems(t.input_schema, 'input_schema', { input: true }),
      ...schemaProblems(t.output_schema ?? undefined, 'output_schema'),
      ...permissionSignals(t),
      ...endpointProblems(t),
      ...(await wardenFindings(warden, t, { id: source, name: t.source_hub_name || hostOf(source), url: source })),
    ]);
    items.push({
      kind: 'listing', status, key, source, ours: isOurs(source), source_name: t.source_hub_name || hostOf(source),
      product_id: t.product_id, capability_id: t.capability_id, name: t.display_name || t.name,
      price_usd: t.price_per_call_usd, invoke_url: t.invoke_url ?? null,
      changed_fields: status === 'changed' ? changedFields(was.view, fingerprintedView(view)) : [],
      description: clip(t.description), worst: worst(findings), findings,
    });
  }
  for (const key of Object.keys(prev.listings)) if (!next.listings[key]) counts.removed += 1;

  const allPeers = [...(peers?.peers ?? []).map((p) => ({ ...p, status: p.status || 'active' })), ...(peers?.pending ?? []).map((p) => ({ ...p, status: p.status || 'pending' }))];
  for (const p of allPeers) {
    if (!p.url) continue;
    const view = { status: p.status, name: p.name ?? '', description: p.declared?.description ?? '', public_key: p.public_key ?? '' };
    const fp = fingerprint(view);
    const was = prev.peers[p.url];
    next.peers[p.url] = { fp, status: p.status, view: fingerprintedView(view), firstSeen: was?.firstSeen ?? at };
    const status = baseline ? 'baseline' : !was ? 'new' : was.fp !== fp ? 'changed' : null;
    if (status === 'new') counts.peersNew += 1;
    if (status === 'changed') counts.peersChanged += 1;
    if (!status) continue;
    const findings = [];
    if (hostOf(p.url) && !String(p.url).startsWith('https://')) findings.push(finding('endpoint', 'not_https', 'high', 'url', 'the hub is not on https'));
    if (p.pin_reject_reason) findings.push(finding('identity', 'pin_rejected', 'medium', 'public_key', clip(String(p.pin_reject_reason), 200)));
    if (p.identity_key_matches === false) findings.push(finding('identity', 'identity_key_mismatch', 'medium', 'public_key', 'the key the hub advertises differs from the pinned one'));
    if (view.description) {
      findings.push(...await wardenFindings(warden, { name: p.name || hostOf(p.url), description: view.description, input_schema: {} }, { id: p.url, name: p.name || hostOf(p.url), url: p.url }));
    }
    items.push({
      kind: 'peer', status, key: p.url, source: p.url, ours: isOurs(p.url), source_name: p.name || hostOf(p.url),
      peer_status: p.status, capabilities: p.capabilities_count ?? null, categories: p.categories ?? [], last_crawl: p.last_crawl || null,
      changed_fields: status === 'changed' ? changedFields(was?.view, fingerprintedView(view)) : [],
      description: clip(view.description), worst: worst(findings), findings: sortFindings(findings),
    });
  }

  for (const s of observed?.sellers ?? []) {
    for (const r of s.routes ?? []) {
      const key = r.url;
      if (!key) continue;
      const view = { description: r.description ?? '', price_usd: r.price_usd ?? null, listed_price_usd: r.listed_price_usd ?? null, pay_to: r.pay_to ?? '', network: r.network ?? '' };
      const fp = fingerprint(view);
      const was = prev.routes[key];
      next.routes[key] = { fp, firstSeen: was?.firstSeen ?? at };
      const status = baseline ? 'baseline' : !was ? 'new' : was.fp !== fp ? 'changed' : null;
      if (status === 'new') counts.routesNew += 1;
      if (status === 'changed') counts.routesChanged += 1;
      if (!status) continue;
      const findings = [];
      if (!String(r.url).startsWith('https://')) findings.push(finding('endpoint', 'not_https', 'high', 'url', 'the route is not on https'));
      if (s.pinned_pay_to && r.pay_to && String(r.pay_to).toLowerCase() !== String(s.pinned_pay_to).toLowerCase()) {
        findings.push(finding('price', 'pay_to_changed', 'high', 'pay_to', 'the 402 names another payee than the pinned one'));
      }
      if (r.price_matches_listing === false) findings.push(finding('price', 'price_differs_from_listing', 'medium', 'price', `402 asks $${r.price_usd}, listing says $${r.listed_price_usd}`));
      if (r.served === false || (r.result && r.result !== 'quoted')) findings.push(finding('endpoint', 'route_not_served', 'low', 'url', `probe result ${r.result ?? 'not served'}`));
      if (String(r.description ?? '').trim().length < 30) findings.push(finding('description', 'thin_description', 'low', 'description', 'too little text for a buyer agent to choose this route'));
      if (r.description) findings.push(...await wardenFindings(warden, { name: String(r.url), description: r.description, input_schema: {} }, { id: s.origin, name: s.name || hostOf(s.origin), url: s.origin }));
      items.push({
        kind: 'observed_route', status, key, source: s.origin, ours: isOurs(s.origin), source_name: s.name || hostOf(s.origin),
        name: `${hostOf(r.url)}${(() => { try { return new URL(r.url).pathname; } catch { return ''; } })()}`,
        price_usd: r.price_usd ?? null, network: r.network ?? '', consent: s.consent ?? null,
        changed_fields: status === 'changed' ? ['description/price/payee'] : [],
        description: clip(r.description), worst: worst(findings), findings: sortFindings(findings),
      });
    }
  }

  const severity = { high: 0, medium: 0, low: 0, info: 0 };
  for (const it of items) for (const f of it.findings) severity[f.severity] += 1;
  // The only findings a welcome letter may use; the model is told to take nothing else from `findings`.
  for (const it of items) {
    it.letter_points = letterPoints(it.findings);
    // A peer the hub never managed to read has no catalogue to welcome; on 2026-11-06 that was every https probe
    // (webhook.site, httpbin and tinyurl redirects, example.com). A real hub is read within hours; if its first day
    // goes unread, its entry shows up again as changed once it publishes a description.
    it.no_welcome_reason = it.ours ? null
      : noWelcomeReason(it.source) ?? (it.kind === 'peer' && !it.last_crawl ? 'not_reached' : null);
  }
  const bySource = new Map();
  for (const it of items) {
    const s = bySource.get(it.source) ?? {
      source: it.source, name: it.source_name, ours: it.ours, items: 0, new: 0, changed: 0, high: 0, medium: 0, letter_points: 0,
      welcome: !it.ours && !it.no_welcome_reason, no_welcome_reason: it.no_welcome_reason,
    };
    s.items += 1;
    if (it.status === 'new') s.new += 1;
    if (it.status === 'changed') s.changed += 1;
    for (const f of it.findings) if (f.severity === 'high' || f.severity === 'medium') s[f.severity] += 1;
    s.letter_points += it.letter_points.length;
    // One item a letter can be about is enough for the source to get one.
    if (!it.ours && !it.no_welcome_reason) Object.assign(s, { welcome: true, no_welcome_reason: null });
    bySource.set(it.source, s);
  }
  // A baseline run shows every outside item and only the problems among ours; a later run shows every new or changed item.
  const shown = baseline ? items.filter((it) => !it.ours || it.worst === 'high' || it.worst === 'medium') : items;
  const report = {
    generatedAt: at,
    baseline,
    hub: hubUrl,
    manifestGeneratedAt: manifest.generated_at ?? null,
    warden: { package: `@aimarket/warden@${warden.version}`, ruleset: `v${warden.ruleset}` },
    counts,
    findings: severity,
    sources: [...bySource.values()].sort((a, b) => Number(a.ours) - Number(b.ours) || b.high - a.high || b.medium - a.medium || a.source.localeCompare(b.source)),
    items: shown.sort((a, b) => Number(a.ours) - Number(b.ours) || SEVERITY_ORDER[a.worst] - SEVERITY_ORDER[b.worst] || a.key.localeCompare(b.key)),
    itemsOmitted: items.length - shown.length,
  };
  return { report, state: next };
}

function fingerprintedView(view) {
  // What the next run compares field by field: hashes, not the text, so the state file stays small.
  return Object.fromEntries(Object.entries(view).map(([k, v]) => [k, fingerprint(v)]));
}

// ── Markdown facts block ───────────────────────────────────────────────────────────────────

function mdEscape(text) {
  return String(text ?? '').replace(/[\r\n]+/g, ' ').replace(/[|`<>]/g, (c) => `\\${c}`).slice(0, 300);
}

export function factsMarkdown(report) {
  const c = report.counts;
  const f = report.findings;
  const lines = [];
  lines.push(`**Факты проверки** (скрипт, не модель) · ${report.generatedAt} · ${report.warden.package}, правила ${report.warden.ruleset}`);
  lines.push('');
  lines.push(report.baseline
    ? `Первый запуск: запомнено ${c.listings} навыков, пиры и x402-продавцы. Ниже — серьёзные и средние находки; остальное в report.json.`
    : `Навыков на хабе ${c.listings}: новых ${c.new}, изменённых ${c.changed}, исчезло ${c.removed}. Пиры: новых ${c.peersNew}, изменённых ${c.peersChanged}. x402-маршруты: новых ${c.routesNew}, изменённых ${c.routesChanged}.`);
  lines.push(`Находки: серьёзных ${f.high}, средних ${f.medium}, мелких ${f.low}, справочных ${f.info}.`);
  lines.push('');
  // A baseline lists only what has a high or medium finding; a later run lists every new or changed item.
  const listed = report.baseline ? report.items.filter((it) => it.worst === 'high' || it.worst === 'medium') : report.items;
  // Items from outside addresses nobody can write to (probes of the hub) are counted on one line, not listed.
  const unaddressed = listed.filter((it) => it.no_welcome_reason);
  const worth = listed.filter((it) => !it.no_welcome_reason);
  const shown = worth.slice(0, MAX_ITEMS_MD);
  for (const it of shown) {
    const head = `- **${mdEscape(it.name || it.source_name || it.key)}** — ${it.kind === 'listing' ? 'навык' : it.kind === 'peer' ? `хаб (${it.peer_status})` : 'x402-маршрут'}, ${it.status}, ${it.ours ? 'наш' : 'внешний'}: ${mdEscape(it.source)}${it.price_usd != null ? `, $${it.price_usd}` : ''}`;
    lines.push(head);
    if (it.changed_fields?.length) lines.push(`  - изменилось: ${mdEscape(it.changed_fields.join(', '))}`);
    const notable = it.findings.filter((x) => x.severity === 'high' || x.severity === 'medium');
    const low = it.findings.filter((x) => x.severity === 'low' && !x.advisory);
    const info = it.findings.filter((x) => x.severity === 'info' && !x.advisory);
    const patterns = it.findings.filter((x) => x.advisory);
    if (!notable.length && !low.length) lines.push('  - проблем не найдено');
    for (const x of notable) lines.push(`  - ${x.severity}: ${x.code} (${mdEscape(x.where)}) — ${mdEscape(x.detail)}`);
    if (low.length) lines.push(`  - мелкое: ${[...new Set(low.map((x) => x.code))].join(', ')}`);
    if (info.length) lines.push(`  - к сведению: ${[...new Set(info.map((x) => x.code))].join(', ')}`);
    if (patterns.length) lines.push(`  - совпадения шаблонов WARDEN, слабый сигнал, не для письма автору: ${[...new Set(patterns.map((x) => x.code))].join(', ')}`);
    if (!it.ours && it.letter_points?.length) lines.push(`  - для письма автору: ${[...new Set(it.letter_points.map((x) => x.code))].join(', ')}`);
  }
  if (worth.length > shown.length) lines.push(`- …и ещё ${worth.length - shown.length} в report.json`);
  if (unaddressed.length) {
    const why = { not_https: 'не https', no_public_name: 'без публичного имени', credentials_in_address: 'с учётными данными в адресе', not_reached: 'хаб ни разу не открылся' };
    const reasons = {};
    for (const it of unaddressed) reasons[it.no_welcome_reason] = (reasons[it.no_welcome_reason] ?? 0) + 1;
    const sev = (s) => unaddressed.reduce((n, it) => n + it.findings.filter((x) => x.severity === s).length, 0);
    lines.push(`- ${unaddressed.length} внешних позиций с ${new Set(unaddressed.map((it) => it.source)).size} адресов, которым не пишем `
      + `(${Object.entries(reasons).map(([k, n]) => `${why[k] ?? k}: ${n}`).join(', ')}) — похоже на пробы хаба; `
      + `находок серьёзных ${sev('high')}, средних ${sev('medium')}; каждая в report.json`);
  }
  if (report.baseline) {
    const quiet = report.items.length - listed.length;
    if (quiet) lines.push(`- ${quiet} внешних позиций только с мелкими замечаниями или без них — в report.json`);
  }
  if (report.itemsOmitted) lines.push(`- ${report.itemsOmitted} наших позиций без серьёзных и средних находок не показаны`);
  lines.push('');
  const outside = report.sources.filter((s) => !s.ours);
  const welcome = outside.filter((s) => s.welcome);
  lines.push('Источники вне экосистемы: ' + (welcome.map((s) => `${mdEscape(s.name)} (${s.items})`).join(', ') || 'нет')
    + (outside.length > welcome.length ? `; адресов, которым не пишем: ${outside.length - welcome.length}` : ''));
  return lines.join('\n') + '\n';
}

// ── CLI ────────────────────────────────────────────────────────────────────────────────────

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const m = /^--([a-z-]+)$/.exec(argv[i]);
    if (!m) throw new Error(`unexpected argument ${argv[i]}`);
    out[m[1]] = argv[i + 1];
    i += 1;
  }
  return out;
}

function writeAtomic(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp-${process.pid}`;
  writeFileSync(tmp, text);
  renameSync(tmp, path);
}

async function main() {
  const a = args(process.argv.slice(2));
  for (const need of ['manifest', 'peers', 'observed', 'state', 'out', 'md']) if (!a[need]) throw new Error(`--${need} is required`);
  const read = (p) => JSON.parse(readFileSync(p, 'utf8'));
  const manifest = read(a.manifest);
  if (!Array.isArray(manifest.tools) || manifest.tools.length === 0) throw new Error('the manifest has no tools: refusing to record an empty market as the new state');
  const state = existsSync(a.state) ? read(a.state) : null;
  const warden = await loadWarden(a.warden);
  const { report, state: next } = await review({ manifest, peers: read(a.peers), observed: read(a.observed), state, now: a.now, warden });
  writeAtomic(a.out, JSON.stringify(report, null, 2) + '\n');
  writeAtomic(a.md, factsMarkdown(report));
  writeAtomic(a.state, JSON.stringify(next) + '\n');
  const c = report.counts;
  process.stdout.write(JSON.stringify({ baseline: report.baseline, listings: c.listings, new: c.new, changed: c.changed, removed: c.removed,
    peersNew: c.peersNew, routesNew: c.routesNew, findings: report.findings, shown: report.items.length }) + '\n');
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  main().catch((err) => {
    process.stderr.write(`supplier review failed: ${err?.message ?? err}\n`);
    process.exit(1);
  });
}
