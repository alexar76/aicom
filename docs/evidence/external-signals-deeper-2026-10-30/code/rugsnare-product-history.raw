import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fetchTools } from './rpc.js';
import { toolHash, schemaHash, proseHash } from './hash.js';
import { annotationsEqual, schemaDiff, schemaNotationDiff, gradeSchemaDrift, detectAdditionalPropertiesDirection, detectPaywallIntroduction } from './pins.js';
import { compareVersions } from './version.js';
import { extractTgz } from './tarball.js';

/**
 * rugsnare history <package> - scan the WHOLE published history of an npm
 * MCP server for silent contract changes.
 *
 * For each version: download the tarball straight from the registry (npm is
 * never invoked, no lifecycle scripts run), extract it with the system tar,
 * spawn the server exactly like an MCP client would, take tools/list, and
 * hash every contract. Consecutive versions are then diffed pair by pair
 * with the same split-hash logic as `rugsnare diff`.
 *
 * This RUNS third-party code locally - the same code you would run by
 * installing the package. Nothing is sent anywhere; everything happens in a
 * throwaway temp directory.
 */

const REGISTRY = 'https://registry.npmjs.org';

/** Accepts "pkg", "@scope/pkg", full npm URLs, and raw config lines like
 *  "npx -y pkg" (runner + flags stripped); returns the bare name. */
export function parsePackageName(input) {
  let s = String(input).trim();
  // strip an npx/uvx-style runner and its leading flags: people paste what
  // their MCP config says, not the bare package name
  const runners = new Set(['npx', 'npm', 'pnpm', 'yarn', 'bunx', 'bun', 'deno', 'uvx', 'pipx', 'dlx']);
  const toks = s.split(/\s+/).filter(Boolean);
  let i = 0;
  if (toks.length > 1 && runners.has(toks[0].toLowerCase())) i = 1;
  while (i < toks.length && (toks[i].startsWith('-') || runners.has(toks[i].toLowerCase()))) i++;
  if (i < toks.length) s = toks[i];

  const urlMatch = s.match(/^https?:\/\/(?:www\.)?npmjs\.com\/package\/((?:@[^/?#]+\/)?[^/?#]+)/i);
  if (urlMatch) s = decodeURIComponent(urlMatch[1]);
  const regMatch = s.match(/^https?:\/\/registry\.npmjs\.org\/((?:@[^/?#]+\/)?[^/?#]+)/i);
  if (regMatch) s = decodeURIComponent(regMatch[1]);
  if (!/^(@[a-z0-9-~][a-z0-9-._~]*\/)?[a-z0-9-~][a-z0-9-._~]*$/i.test(s)) {
    throw new Error(`not a valid npm package name: ${input}`);
  }
  return s;
}

/** Fetch the version->tarball map from the registry (abbreviated metadata). */
export async function fetchRegistryVersions(name, { timeoutMs = 10000 } = {}) {
  // full encodeURIComponent over the whole name: scoped packages become
  // %40scope%2Fname, which the registry accepts as the canonical form.
  // NOTE: full metadata (not the abbreviated install doc) because only it
  // carries the per-version publish timestamps (`time`).
  const res = await fetch(`${REGISTRY}/${encodeURIComponent(name)}`, {
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 404) throw new Error(`package not found on npm: ${name}`);
  if (!res.ok) throw new Error(`registry responded ${res.status}`);
  const body = await res.json();
  const versions = Object.keys(body.versions ?? {});
  versions.sort((a, b) => compareVersions(a, b));
  const dist = {};
  for (const v of versions) dist[v] = body.versions[v]?.dist?.tarball;
  return { versions, dist, latest: body['dist-tags']?.latest ?? versions.at(-1), time: body.time ?? {} };
}

/** Download + extract one version tarball into dir; returns the package root. */
async function extractVersion(tarballUrl, dir, { timeoutMs = 30000 } = {}) {
  const res = await fetchValidated(tarballUrl, 'registry.npmjs.org', timeoutMs);
  const files = extractTgz(Buffer.from(await res.arrayBuffer()));
  // npm tarball members already carry the "package/" prefix - extract into
  // the temp dir itself, every member guarded to stay inside it
  const root = path.resolve(dir);
  let wrote = 0;
  for (const f of files) {
    const dest = path.resolve(root, f.path);
    // path traversal guard: every member must stay inside root
    if (dest !== root && !dest.startsWith(root + path.sep)) continue;
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, f.data);
    wrote++;
  }
  if (wrote === 0) throw new Error('empty tarball');
  return path.join(root, 'package');
}

/**
 * Fetch a tarball following redirects, but re-validating the host after
 * every hop (review 34): a redirect must never smuggle us off the registry.
 */
export async function fetchValidated(url, allowedHost, timeoutMs) {
  let current = url;
  for (let hop = 0; hop < 3; hop++) {
    const u = new URL(current);
    if (u.hostname !== allowedHost) throw new Error(`refusing non-${allowedHost} host: ${u.hostname}`);
    const res = await fetch(u, { redirect: 'manual', signal: AbortSignal.timeout(timeoutMs) });
    if (res.status >= 300 && res.status < 400) {
      const loc = res.headers.get('location');
      if (!loc) throw new Error('redirect without location');
      current = new URL(loc, u).href;
      continue;
    }
    if (!res.ok) throw new Error(`tarball fetch ${res.status}`);
    return res;
  }
  throw new Error('too many redirects');
}

/**
 * The declared launch path (package.json "bin") - R34. Supabase moved its
 * stdio entry (dist/transports/stdio.js -> dist/cli.js in 0.9+) with the
 * tool contract untouched: packaging drift that no schemaHash can see, but
 * every wrapper config, debugger attach and wrapper script keyed on the old
 * path breaks all the same. Captured per version; a move between adjacent
 * versions surfaces as entryChanged on the pair.
 */
export function binPathOf(pkgDir) {
  const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'));
  const bin = pkg.bin;
  if (typeof bin === 'string') return bin;
  if (bin && typeof bin === 'object') return Object.values(bin)[0];
  return null;
}

/** Resolve the server entry from the extracted package.json bin field. */
function serverEntry(pkgDir) {
  const rel = binPathOf(pkgDir);
  if (!rel) throw new Error('no bin in package.json (not a runnable MCP server?)');
  return path.join(pkgDir, rel);
}

/**
 * Install production deps of the extracted package WITHOUT running any
 * lifecycle script (--ignore-scripts).
 *
 * R32: STRICT resolution first, --legacy-peer-deps as a FALLBACK (not the
 * default). Reason: the contract a server serves can depend on which
 * in-range dependency minor npm resolves - mongodb-mcp-server 2.1.2 declares
 * zod ^4.4.3 and served materially different inputSchema depending on the
 * resolved zod (found live by the 1.3.0 release re-run). A strict install
 * matches what a plain user install resolves; the legacy fallback stays for
 * peer-conflicting packages (common among Claude Code companions), and the
 * captured contract is marked legacy-resolved so consumers know the tree
 * may differ. Command and arguments are fully static literals; the only
 * dynamic input is cwd (a temp dir we created).
 */
const NPM_INSTALL_BASE = ['install', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund', '--loglevel=error'];

/**
 * R32: schema-affecting dependencies whose RESOLVED version at install time
 * can change the captured contract. Recorded next to every captured version
 * ("captured against zod X.Y.Z") so pair diffs can attribute schema changes
 * to dependency drift instead of server code.
 */
export const SCHEMA_DEPS = [
  'zod',
  'ajv',
  '@sinclair/typebox',
  '@modelcontextprotocol/sdk',
  '@modelcontextprotocol/node',
];

/** Read the resolved versions of SCHEMA_DEPS from an installed tree. */
export function resolvedSchemaDeps(pkgDir) {
  const out = {};
  for (const dep of SCHEMA_DEPS) {
    try {
      const pj = JSON.parse(fs.readFileSync(path.join(pkgDir, 'node_modules', dep, 'package.json'), 'utf8'));
      if (pj.version) out[dep] = pj.version;
    } catch { /* not installed - not every server uses every schema lib */ }
  }
  return out;
}

/** Pure diff of two resolved-dep maps: [{dep, from, to}] where they differ. */
export function depChangesBetween(oldDeps = {}, newDeps = {}) {
  const changed = [];
  for (const dep of [...new Set([...Object.keys(oldDeps), ...Object.keys(newDeps)])]) {
    if (oldDeps[dep] !== newDeps[dep]) {
      changed.push({ dep, from: oldDeps[dep] ?? null, to: newDeps[dep] ?? null });
    }
  }
  return changed;
}

/**
 * Stub env var NAMES for credential-gated servers (P3 followup, proven in
 * the field by the Oct 2026 audit): many MCP servers validate only the
 * PRESENCE of an API key at boot - a dummy marker value lets tools/list
 * enumerate without any real credential. Var names only; the value is a
 * fixed non-secret marker string, not a credential.
 */
export const STUB_ENV_VARS = [
  'CURRENTS_API_KEY',
  'CURRENTS_PROJECT_ID',
  'HOSTINGER_API_KEY',
  'AZURE_DEVOPS_EXT_PAT',
  'PRIVATE_APP_ACCESS_TOKEN',
];
const STUB_MARKER = 'rugsnare_stub';

function buildStubEnv() {
  const env = {};
  for (const name of STUB_ENV_VARS) env[name] = STUB_MARKER;
  return env;
}

function runNpmInstall(pkgDir, extraArgs) {
  const npmCli = path.join(path.dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js');
  const useCli = fs.existsSync(npmCli);
  const base = useCli ? [npmCli, ...NPM_INSTALL_BASE, ...extraArgs] : [...NPM_INSTALL_BASE, ...extraArgs];
  const cmd = useCli ? process.execPath : 'npm';
  return new Promise((resolve, reject) => {
    execFile(cmd, base, { cwd: pkgDir, timeout: 120000, windowsHide: true }, (err, _so, se) => {
      if (err) reject(new Error(`npm install: ${(se || err.message).split('\n')[0]}`));
      else resolve();
    });
  });
}

/** Strict install first; --legacy-peer-deps only on ERESOLVE. Returns the mode. */
async function installDeps(pkgDir) {
  try {
    await runNpmInstall(pkgDir, []);
    return 'strict';
  } catch (e) {
    if (!/ERESOLVE|peer dep/i.test(String(e.message))) throw e;
    await runNpmInstall(pkgDir, ['--legacy-peer-deps']);
    return 'legacy';
  }
}

/** List the tool contracts of one version by actually running it. */
export async function contractOfVersion(name, version, tarballUrl, { timeoutMs = 15000, stubEnv = false, serverArgs = [] } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `rugsnare-hist-${version}-`));
  try {
    const pkgDir = await extractVersion(tarballUrl, dir);
    // R32: capture the resolved schema-dep versions NEXT TO the contract -
    // a floating zod range can rewrite a server's contract with no server
    // release, and pair diffs must be able to attribute changes to dep
    // drift rather than server code.
    const depResolution = await installDeps(pkgDir);
    const deps = resolvedSchemaDeps(pkgDir);
    // R34: the declared launch path travels with the contract - packaging
    // drift (a moved bin) is invisible to schemaHash but breaks everything
    // keyed on the old path
    const binPath = binPathOf(pkgDir);
    const entry = serverEntry(pkgDir);
    // serverArgs: per-package launch arguments (e.g. LaunchDarkly needs
    // "start --transport stdio --api-key <key>"). Passed as a fixed array
    // after the entry point - no shell, no interpolation.
    const { tools } = await fetchTools({
      command: process.execPath,
      args: [entry, ...serverArgs],
      env: { ...process.env, RUGSNARE_HISTORY: version, ...(stubEnv ? buildStubEnv() : {}) },
      cwd: pkgDir,
      timeoutMs,
    });
    const pins = {};
    for (const t of tools || []) {
      pins[t.name] = {
        hash: toolHash(t),
        schemaHash: schemaHash(t),
        proseHash: proseHash(t),
        description: t.description ?? '',
        inputSchema: t.inputSchema,
        annotations: t.annotations,
      };
    }
    return { version, tools: pins, toolCount: (tools || []).length, deps, depResolution, binPath };
  } finally {
    try { fs.rmSync(dir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 }); } catch { /* Windows */ }
  }
}

/**
 * Diff two consecutive version contracts. Returns findings in the same
 * shape as compareTools: { tool, status, driftType, oldDescription, newDescription }.
 * Annotation-only flips (e.g. a dropped destructiveHint) are DRIFT/ANNOTATION,
 * mirroring `rugsnare diff`.
 */
export function diffVersionContracts(older, newer) {
  const findings = [];
  const a = older.tools ?? {};
  const b = newer.tools ?? {};
  for (const [name, pin] of Object.entries(b)) {
    const prev = a[name];
    if (!prev) { findings.push({ tool: name, status: 'NEW' }); continue; }
    if (prev.hash === pin.hash) {
      // byte-identical text+schema, but behavioral hints may have flipped
      if (prev.annotations !== undefined || pin.annotations !== undefined) {
        if (!annotationsEqual(prev.annotations, pin.annotations)) {
          findings.push({
            tool: name,
            status: 'DRIFT',
            driftType: 'ANNOTATION',
            oldDescription: prev.description,
            newDescription: pin.description,
          });
        }
      }
      continue;
    }
    const schemaChanged = prev.schemaHash !== pin.schemaHash;
    // P4 direction-aware gradation (same rules as `rugsnare diff`):
    // tighten → BREAKING, loosen → LOOSENED, neither → NOTATION
    const paramChanges = schemaChanged && prev.inputSchema && pin.inputSchema
      ? schemaDiff(prev.inputSchema, pin.inputSchema) : [];
    // additionalProperties direction (moved from notation to grading)
    const apChange = schemaChanged && prev.inputSchema && pin.inputSchema
      ? detectAdditionalPropertiesDirection(prev.inputSchema, pin.inputSchema) : null;
    if (apChange) paramChanges.push(apChange);
    const notationChanges = schemaChanged && paramChanges.length === 0 && prev.inputSchema && pin.inputSchema
      ? schemaNotationDiff(prev.inputSchema, pin.inputSchema) : [];
    const driftType = schemaChanged
      ? gradeSchemaDrift(paramChanges, notationChanges)
      : 'COSMETIC';
    // R31 parity with `rugsnare diff`: paywall introduction is a prose-level
    // flag on any drift (schema-silent rewrites grade COSMETIC otherwise)
    const paywall = detectPaywallIntroduction(prev.description, pin.description);
    findings.push({
      tool: name,
      status: 'DRIFT',
      driftType,
      schemaChanges: paramChanges,
      ...(notationChanges.length ? { notationChanges } : {}),
      ...(paywall ? { paywallWarning: paywall.text } : {}),
      oldDescription: prev.description,
      newDescription: pin.description,
    });
  }
  for (const name of Object.keys(a)) {
    if (!b[name]) findings.push({ tool: name, status: 'REMOVED' });
  }

  // R11: rename inference - collapse GONE+NEW pairs with identical contracts
  // into "REnamed a -> b". The azure-devops flagship case (75 GONE + 29 NEW)
  // is mostly renames; this turns 104 lines into ~10 "renamed", ~5 "gone",
  // ~29 "new" - the first thing a maintainer would ask about.
  inferRenames(findings, a, b);

  // R2: cross-tool branch movement - a union branch (operation) that
  // disappeared from one tool and appeared in another = "moved", not
  // removed+added. Netlify case: initialize-database moved from updater
  // tool to reader tool.
  inferBranchMoves(findings, a, b);

  return findings;
}

/**
 * R2: detect union branches (operations) that moved between tools.
 * When a schemaChanges entry says "removed anyOf branch 'X'" on one tool
 * and another tool has "added anyOf branch 'X'" - same const value -
 * annotate both as MOVED rather than removed+added.
 */
function inferBranchMoves(findings, olderTools, newerTools) {
  // collect removed and added branches across all findings
  const removedBranches = []; // {tool, branchName, finding}
  const addedBranches = [];   // {tool, branchName, finding}

  for (const f of findings) {
    if (!f.schemaChanges || !Array.isArray(f.schemaChanges)) continue;
    for (const sc of f.schemaChanges) {
      const text = typeof sc === 'string' ? sc : sc.text ?? '';
      const removedMatch = text.match(/removed (anyOf|oneOf) branch '([^']+)'/);
      if (removedMatch) removedBranches.push({ tool: f.tool, branch: removedMatch[2], finding: f, change: sc });
      const addedMatch = text.match(/added (anyOf|oneOf) branch '([^']+)'/);
      if (addedMatch) addedBranches.push({ tool: f.tool, branch: addedMatch[2], finding: f, change: sc });
    }
  }

  // match by branch name (const discriminator)
  const usedAdded = new Set();
  for (const rb of removedBranches) {
    for (const ab of addedBranches) {
      if (usedAdded.has(ab)) continue;
      if (rb.branch === ab.branch && rb.tool !== ab.tool) {
        // same operation, different tool = moved
        rb.change.text = `moved branch '${rb.branch}' from this tool to '${ab.tool}'`;
        rb.change.direction = 'loosen';
        rb.change.branchMoved = { from: rb.tool, to: ab.tool };
        ab.change.text = `moved branch '${ab.branch}' from '${rb.tool}' to this tool`;
        ab.change.direction = 'expand';
        ab.change.branchMoved = { from: rb.tool, to: ab.tool };
        usedAdded.add(ab);
        break;
      }
    }
  }
}

/**
 * R11: find GONE tools whose (schemaHash, proseHash) matches a NEW tool -
 * identical contract under a different name = likely rename. Collapse the
 * pair into a single RENAMED finding. Also catch near-matches by name
 * pattern (common prefix/suffix swap) when hashes match.
 */
function inferRenames(findings, olderTools, newerTools) {
  const gone = findings.filter((f) => f.status === 'REMOVED');
  const news = findings.filter((f) => f.status === 'NEW');
  if (gone.length === 0 || news.length === 0) return;

  const usedNew = new Set();
  for (const g of gone) {
    const oldPin = olderTools[g.tool];
    if (!oldPin) continue;
    for (const n of news) {
      if (usedNew.has(n.tool)) continue;
      const newPin = newerTools[n.tool];
      if (!newPin) continue;
      // exact hash match = same contract, different name
      if (oldPin.schemaHash === newPin.schemaHash && oldPin.proseHash === newPin.proseHash) {
        g.status = 'RENAMED';
        g.renamedTo = n.tool;
        n.status = 'RENAMED';
        n.renamedFrom = g.tool;
        usedNew.add(n.tool);
        break;
      }
    }
  }
  // remove NEW entries that were consumed by renames
  for (let i = findings.length - 1; i >= 0; i--) {
    if (findings[i].status === 'RENAMED' && findings[i].renamedFrom) {
      // this was a NEW that got consumed; remove the NEW-side entry
      // (the RENAMED info is on the GONE-side entry)
      findings.splice(i, 1);
    }
  }
}

/**
 * R12: classify WHY a version is unreachable - a remote kill-switch
 * (server fetches a manifest and refuses to start on "outdated" versions)
 * is a different finding than a crash or a git-deps install failure.
 * Live example: bybit-mcp pulls api.bybit.com and exits on older versions.
 */
export function classifyUnreachable(errorMessage) {
  const msg = String(errorMessage ?? '');
  // kill-switch / forced-update patterns
  if (/update (is )?required|version (check|too old|outdated)|must (be|upgrade to).*latest|forced update/i.test(msg)) {
    return { cause: 'KILLSWITCH', detail: 'server requires an update - remote kill-switch or forced-upgrade gate' };
  }
  if (/fetch.*(manifest|version|config).*(url|endpoint|api\.)|https?:\/\/api\.[^/]+\//i.test(msg)) {
    return { cause: 'GATED', detail: 'server fetches a remote manifest/config before starting - possible kill-switch' };
  }
  // install failures
  if (/EUNSUPPORTEDPROTOCOL|git dependency|git\+/i.test(msg)) {
    return { cause: 'GIT_DEPS', detail: 'package has git dependencies that npm cannot resolve' };
  }
  // startup failures
  if (/exited early|crashed|signal/i.test(msg)) {
    return { cause: 'CRASH', detail: 'server process exited during startup' };
  }
  if (/timeout|timed out/i.test(msg)) {
    return { cause: 'TIMEOUT', detail: 'server did not respond within the timeout window' };
  }
  return { cause: 'UNKNOWN', detail: null };
}

/**
 * Full history scan. last N published versions (default 10). Versions that
 * fail to start are reported honestly, not silently skipped.
 */
export async function scanHistory(name, { last = 10, from, to, timeoutMs = 15000, stubEnv = false, serverArgs = [], onProgress = () => {} } = {}) {
  const { versions, dist, latest, time } = await fetchRegistryVersions(name);
  // --from/--to: inclusive semver window (surveys quote exact ranges);
  // falls back to the last N when no window is given
  const inWindow = versions.filter((v) =>
    (!from || compareVersions(v, from) >= 0) && (!to || compareVersions(v, to) <= 0));

  // R10: sort by PUBLISH TIME, not semver. Packages with two versioning
  // epochs (e.g. @playwright/mcp: 1.52.0-alpha from March 2025 is
  // semver-OLDER than 0.0.x from 2026) get their histories glued
  // incorrectly by semver sort - a phantom pair appears across epochs.
  // The `time` map is already loaded from the registry; fall back to
  // semver order when a version has no timestamp.
  const byTime = [...inWindow].sort((a, b) => {
    const ta = time[a] ? new Date(time[a]).getTime() : Infinity;
    const tb = time[b] ? new Date(time[b]).getTime() : Infinity;
    if (ta !== tb) return ta - tb;
    return compareVersions(a, b); // same/missing timestamp: semver as tiebreak
  });
  const chosen = byTime.slice(-last);
  onProgress(`${chosen.length} version(s) to check: ${chosen[0]} .. ${chosen.at(-1)} (latest: ${latest})${stubEnv ? ' [stub-env]' : ''}`);

  const ran = [];
  const unreachable = [];
  for (const v of chosen) {
    onProgress(`running ${v} ...`);
    try {
      const c = await contractOfVersion(name, v, dist[v], { timeoutMs, stubEnv, serverArgs });
      ran.push(c);
    } catch (e) {
      unreachable.push({ version: v, reason: e.message, ...classifyUnreachable(e.message) });
    }
  }

  const pairs = [];
  for (let i = 1; i < ran.length; i++) {
    const findings = diffVersionContracts(ran[i - 1], ran[i]);
    // R32 provenance: which schema deps each side was captured against, and
    // where they differ - part of the pair's diff may be dep drift, not
    // server code (mongodb 2.1.2 + floating zod taught us this live)
    const depsChanged = depChangesBetween(ran[i - 1].deps ?? {}, ran[i].deps ?? {});
    // strict vs legacy resolution is provenance too: a legacy-resolved tree
    // may differ from a plain user install, and consumers deserve the marker
    const fromRes = ran[i - 1].depResolution ?? 'strict';
    const toRes = ran[i].depResolution ?? 'strict';
    // R34: launch entry moved between adjacent versions (supabase:
    // dist/transports/stdio.js -> dist/cli.js, contracts identical)
    const entryChanged = ran[i - 1].binPath && ran[i].binPath && ran[i - 1].binPath !== ran[i].binPath
      ? { from: ran[i - 1].binPath, to: ran[i].binPath } : null;
    pairs.push({
      from: ran[i - 1].version,
      to: ran[i].version,
      toPublishedAt: time[ran[i].version] ?? null,
      deps: { from: ran[i - 1].deps ?? {}, to: ran[i].deps ?? {}, fromResolution: fromRes, toResolution: toRes },
      ...(depsChanged.length ? { depsChanged } : {}),
      ...(entryChanged ? { entryChanged } : {}),
      findings,
    });
  }

  const silentChanges = pairs.reduce((n, p) => n + p.findings.length, 0);
  return {
    package: name,
    checked: ran.length,
    planned: chosen.length,
    unreachable,
    pairs,
    silentChanges,
    // a scan where NOTHING could be started must never read as clean -
    // "no data" is not "no changes" (review 34)
    clean: ran.length > 0 && silentChanges === 0,
  };
}
