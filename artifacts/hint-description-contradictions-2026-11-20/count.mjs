#!/usr/bin/env node
// Runs WARDEN's hintContradictions over the corpus from extract.py and counts matches per claim, per server and per
// host. usage: node count.mjs <warden dist dir> <corpus.jsonl> [<out.json>] [--sample N]
import { readFileSync, writeFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { createReadStream } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const [dist, corpus, out] = process.argv.slice(2);
const sampleN = Number(process.argv[process.argv.indexOf("--sample") + 1]) || 0;
const { hintContradictions } = await import(pathToFileURL(resolve(dist, "hint-claims.js")).href);

const host = ep => { try { return ep.startsWith("http") ? new URL(ep).hostname : ep; } catch { return ep; } };
const n = { rows: 0, readOnly: 0, notDestructive: 0 };
const hit = { readOnly: [], notDestructive: [] };
const servers = { readOnly: new Set(), notDestructive: new Set() };
const hosts = { readOnly: new Set(), notDestructive: new Set() };
const corpusServers = new Set();
const rl = createInterface({ input: createReadStream(corpus, "utf8"), crlfDelay: Infinity });
for await (const line of rl) {
  if (!line) continue;
  const r = JSON.parse(line);
  n.rows++;
  corpusServers.add(r.server);
  const ro = r.annotations.readOnlyHint === true;
  const key = ro ? "readOnly" : "notDestructive";
  if (!ro && r.annotations.destructiveHint !== false) continue;
  n[key]++;
  const found = hintContradictions({ name: r.tool, description: r.description, annotations: r.annotations });
  if (!found.length) continue;
  hit[key].push({ server: r.server, endpoint: r.endpoint, tool: r.tool, says: found[0].says, quote: found[0].quote });
  servers[key].add(r.server);
  hosts[key].add(host(r.endpoint));
}
const result = {
  corpus: { tools: n.rows, servers: corpusServers.size, readOnlyHintTrue: n.readOnly, destructiveHintFalseNotReadOnly: n.notDestructive },
  readOnlyHintTrue: { tools: hit.readOnly.length, servers: servers.readOnly.size, hosts: hosts.readOnly.size },
  destructiveHintFalse: { tools: hit.notDestructive.length, servers: servers.notDestructive.size, hosts: hosts.notDestructive.size },
  bySays: Object.fromEntries(["readOnly", "notDestructive"].map(k => [k, Object.entries(hit[k].reduce((m, h) => (m[h.says] = (m[h.says] ?? 0) + 1, m), {})).sort((a, b) => b[1] - a[1])])),
};
console.log(JSON.stringify(result, null, 1));
if (out) writeFileSync(out, JSON.stringify({ ...result, matches: hit }, null, 1));
if (sampleN) {
  // A fixed-stride sample (every k-th match), so a re-run reads the same rows.
  for (const k of ["readOnly", "notDestructive"]) {
    const h = hit[k], step = Math.max(1, Math.floor(h.length / sampleN));
    console.log(`--- sample ${k}`);
    for (let i = 0; i < h.length && i / step < sampleN; i += step) console.log(`${h[i].tool} [${h[i].says}] ${h[i].quote}`);
  }
}
