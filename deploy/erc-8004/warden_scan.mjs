// WARDEN scan of harvested tools/list results: node warden_scan.mjs TOOLS.jsonl OUT.json <path to @aimarket/warden dist/index.js>

import { readFileSync, writeFileSync } from "node:fs";
const W = await import(process.argv[4]);
const { StaticScanGate, ThreatGate, ThreatFeed, staticScanRulesetRef, STATIC_SCAN_RULESET_VERSION } = W;
const policy = { blockAtSeverity: "high", sensitiveToolPatterns: ["*delete*", "*transfer*", "*key*", "*secret*"], allowUnknownServers: true, pinToolDefs: false };
const ss = new StaticScanGate(), th = new ThreatGate(new ThreatFeed({}));
const RANK = { info: 0, low: 1, medium: 2, high: 3, critical: 4 };
const rows = [];
for (const line of readFileSync(process.argv[2], "utf8").split("\n")) {
  if (!line.trim()) continue;
  const rec = JSON.parse(line);
  if (rec.status !== "ok" || !rec.tools.length) { rows.push({ agent_id: rec.agent_id, title: rec.title, url: rec.url, status: rec.status }); continue; }
  const input = { server: { id: rec.name, name: rec.server_info?.name ?? rec.title, transport: "http", url: rec.url }, tools: rec.tools, prior: [], policy };
  const a = await ss.evaluate(input); const b = await th.evaluate({ ...input, prior: a.findings });
  const findings = [...a.findings, ...b.findings];
  const blocking = findings.filter((f) => !f.advisory && RANK[f.severity] >= RANK.high);
  rows.push({ agent_id: rec.agent_id, title: rec.title, url: rec.url, status: "ok", tools: rec.tools.length,
    score: Math.round(a.score * b.score * 100), wouldBlock: blocking.length > 0 || Boolean(a.fatal || b.fatal),
    blocking: blocking.map((f) => ({ code: f.code, severity: f.severity, tool: f.tool, message: f.message })),
    advisory: findings.length - blocking.length });
}
writeFileSync(process.argv[3], JSON.stringify({ warden: JSON.parse(readFileSync(process.argv[4].replace(/dist\/index\.js$/, "package.json"), "utf8")).version, ruleset: { version: STATIC_SCAN_RULESET_VERSION, ref: staticScanRulesetRef() }, rows }, null, 1));
for (const r of rows) console.log(r.agent_id, (r.title || "").slice(0, 26), "|", r.status, r.tools ?? "", r.score ?? "", r.wouldBlock ? "BLOCK" : "", (r.blocking || []).map((f) => `${f.code}@${f.tool}`).join(","));
