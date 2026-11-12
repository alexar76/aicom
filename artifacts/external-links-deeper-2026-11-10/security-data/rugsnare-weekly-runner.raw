#!/usr/bin/env node
// run-weekly-audit.mjs - pin every server in watch-list.json, install latest, diff, write WEEKLY.md.
// Runs the exact flow documented in audits/npm-top-mcp-drift-2026-10.md. Never fails the CI job
// itself: per-server failures become SKIP entries in the report.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const work = join(here, '.weekly-work');
const list = JSON.parse(readFileSync(join(here, 'watch-list.json'), 'utf8')).servers;

function sh(cmd, opts = {}) {
  // { ...; } 2>&1: redirection must cover the WHOLE chain - rugsnare prints its
  // DRIFT DETECTED summary to stderr, and appending 2>&1 to the command string
  // would bind it to the last statement only
  try { return { ok: true, out: execFileSync('bash', ['-c', '{ ' + cmd + '; } 2>&1'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 15 * 60 * 1000, ...opts }) }; }
  catch (e) { return { ok: false, out: (e.stdout || '') + (e.stderr || ''), code: e.status }; }
}

mkdirSync(work, { recursive: true });
process.chdir(work);

const results = [];
for (const s of list) {
  const entry = { server: s.name, package: s.package, pinned: s.pinned, latest: null, findings: null, status: 'ok', excerpt: [] };
  try {
    // resolve latest (via sh: execFileSync('npm') fails with ENOENT on Windows)
    entry.latest = sh(`npm view ${s.package} version`).out.trim().split('\n').pop() || null;

    // mcp.json (always fresh per server)
    const cfg = { mcpServers: { [s.name]: { command: 'node', args: [s.entry, ...(s.args || [])], env: s.env || {} } } };
    writeFileSync(join(work, 'mcp.json'), JSON.stringify(cfg, null, 2));
    sh('rm -rf .rugsnare node_modules package.json package-lock.json');

    // pin the baseline
    sh(`npm i --ignore-scripts ${s.package}@${s.pinned}`);
    const scan = sh('rugsnare scan --config mcp.json');
    if (!scan.ok) { entry.status = 'scan-failed'; entry.excerpt = [scan.out.trim().split('\n').slice(-2).join('\n')]; results.push(entry); continue; }

    // update to latest, rebuild natives best-effort
    sh(`npm i --ignore-scripts ${s.package}@${entry.latest}`);
    sh('npm rebuild keytar'); // no-op when absent
    const diff = sh('rugsnare diff --config mcp.json; echo "EXIT:$?"');

    const m = diff.out.match(/DRIFT DETECTED \((\d+) finding/);
    entry.findings = m ? Number(m[1]) : 0;
    entry.clean = /rugsnare diff: clean/.test(diff.out);
    entry.excerpt = diff.out.split('\n').filter(l => /\[DRIFT\]|\[NEW \]|\[GONE\]/.test(l)).slice(0, 12);
    if (!m && !entry.clean) entry.status = 'diff-failed';
  } catch (e) {
    entry.status = 'error: ' + String(e.message).slice(0, 120);
  }
  results.push(entry);
}

// report
const now = new Date().toISOString().slice(0, 10);
const total = results.reduce((a, r) => a + (r.findings || 0), 0);
let md = `# MCP Drift Watch - weekly report\n\n`;
md += `**Run:** ${now} · pinned baselines from \`audits/watch-list.json\` (advance a pin deliberately, via PR, when you accept a new contract). Method: pin -> install latest -> \`rugsnare diff\`.\n\n`;
md += `**Total findings since baselines: ${total}**\n\n`;
md += `| server | package | pinned -> latest | findings | status |\n|---|---|---|---|---|\n`;
for (const r of results) {
  md += `| ${r.server} | ${r.package} | ${r.pinned} -> ${r.latest || '?'} | ${r.findings ?? '-'} | ${r.clean ? 'clean' : r.status} |\n`;
}
md += `\nFull audit with receipts: [npm-top-mcp-drift-2026-10.md](npm-top-mcp-drift-2026-10.md). Tool: [rugsnare](https://www.npmjs.com/package/rugsnare).\n`;
for (const r of results) {
  if (r.excerpt && r.excerpt.length) {
    md += `\n## ${r.server} - drift excerpt\n\n\`\`\`\n${r.excerpt.join('\n')}\n\`\`\`\n`;
  }
}
writeFileSync(join(here, 'WEEKLY.md'), md);
console.log(md);
