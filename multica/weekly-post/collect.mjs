#!/usr/bin/env node
// Weekly build-in-public facts — the deterministic half of the Multica agent «недельный пост».
//
// Collects what our Multica agents did in the last 7 days (their tasks and final answers, read with the
// `multica` CLI) and how the hubs moved (public /ai-market/v2/stats/live counters, downloaded by run.sh),
// and compares the hub counters with last week's snapshot. The model writes the post from week.json and
// pastes facts.md unchanged, so every number in the draft has a source a reader can check.
//
//   node collect.mjs --stats-dir DIR --state snapshots.json --out week.json --md facts.md [--now ISO]
//
// DIR holds one <host>.json per hub (the stats/live document). Nothing here sends anything anywhere.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';

export const WEEK_MS = 7 * 24 * 3600 * 1000;
const MAX_ANSWER = 1500;
const COUNTERS = ['total_invocations', 'external_invocations', 'operator_self_invocations', 'successful_invocations',
  'failed_invocations', 'volume_total_usd', 'settled_volume_usd', 'capabilities_count', 'peers_count'];

function clip(text, max = MAX_ANSWER) {
  const s = String(text ?? '');
  return s.length > max ? s.slice(0, max) + ` …[+${s.length - max} chars]` : s;
}

function round(n, digits = 4) {
  return typeof n === 'number' && Number.isFinite(n) ? Math.round(n * 10 ** digits) / 10 ** digits : null;
}

/** Counters of one hub now, and their change since the last snapshot (null on the first run). */
export function hubWeek(host, stats, previous) {
  const s = stats?.summary ?? {};
  const now = Object.fromEntries(COUNTERS.map((k) => [k, typeof s[k] === 'number' ? s[k] : null]));
  const delta = previous
    ? Object.fromEntries(COUNTERS.map((k) => [k, now[k] != null && previous.counters?.[k] != null ? round(now[k] - previous.counters[k]) : null]))
    : null;
  return {
    host, counters: now, since: previous?.at ?? null, delta,
    last24h: { invocations: s.invocations_24h ?? null, volume_usd: s.volume_24h_usd ?? null, p95_latency_ms: s.p95_latency_ms_24h ?? null },
  };
}

/** Our agents' tasks created in the window, with each task's last answer by an agent. */
export function agentWeek({ agents, issues, commentsByIssue, from, to }) {
  const byAgent = new Map(agents.map((a) => [a.id, { id: a.id, name: a.name, runs: 0, statuses: {}, tasks: [] }]));
  for (const issue of issues) {
    const at = Date.parse(issue.created_at);
    if (!(at >= from && at < to) || issue.assignee_type !== 'agent' || !byAgent.has(issue.assignee_id)) continue;
    const a = byAgent.get(issue.assignee_id);
    a.runs += 1;
    a.statuses[issue.status] = (a.statuses[issue.status] ?? 0) + 1;
    const answers = (commentsByIssue[issue.id] ?? []).filter((c) => c.author_type === 'agent' && c.author_id === issue.assignee_id);
    const last = answers.sort((x, y) => Date.parse(x.created_at) - Date.parse(y.created_at)).at(-1);
    a.tasks.push({ identifier: issue.identifier, title: issue.title, status: issue.status, created_at: issue.created_at, answer: last ? clip(last.content) : null });
  }
  for (const a of byAgent.values()) a.tasks.sort((x, y) => Date.parse(x.created_at) - Date.parse(y.created_at));
  return [...byAgent.values()];
}

export function collect({ agents, issues, commentsByIssue, stats, state, now }) {
  const to = Date.parse(now);
  const from = to - WEEK_MS;
  const hubs = Object.keys(stats).sort().map((host) => hubWeek(host, stats[host], state?.hubs?.[host]));
  const week = {
    period: { from: new Date(from).toISOString(), to: new Date(to).toISOString() },
    firstSnapshot: !state,
    hubs,
    agents: agentWeek({ agents, issues, commentsByIssue, from, to }),
  };
  const next = { version: 1, at: week.period.to, hubs: Object.fromEntries(hubs.map((h) => [h.host, { at: week.period.to, counters: h.counters }])) };
  return { week, state: next };
}

function money(n) {
  return n == null ? '—' : `$${round(n, 4)}`;
}

function num(n) {
  return n == null ? '—' : String(n);
}

export function factsMarkdown(week) {
  const lines = [];
  lines.push(`**Факты недели** (скрипт, не модель) · ${week.period.from.slice(0, 10)} — ${week.period.to.slice(0, 10)} UTC`);
  lines.push('');
  lines.push('Хабы (публичные счётчики `/ai-market/v2/stats/live`):');
  for (const h of week.hubs) {
    const c = h.counters;
    if (h.delta) {
      const d = h.delta;
      lines.push(`- ${h.host}: с ${String(h.since ?? '').slice(0, 10)} вызовов ${num(d.total_invocations)} (внешних ${num(d.external_invocations)}, своих ${num(d.operator_self_invocations)}), успешных ${num(d.successful_invocations)}, ошибок ${num(d.failed_invocations)}, оборот ${money(d.volume_total_usd)}; навыков ${num(c.capabilities_count)}, пиров ${num(c.peers_count)}`);
    } else {
      lines.push(`- ${h.host}: первый снимок, разница будет через неделю. За всё время вызовов ${num(c.total_invocations)} (внешних ${num(c.external_invocations)}, своих ${num(c.operator_self_invocations)}), оборот ${money(c.volume_total_usd)}; за 24 ч вызовов ${num(h.last24h.invocations)}; навыков ${num(c.capabilities_count)}, пиров ${num(c.peers_count)}`);
    }
  }
  lines.push('');
  lines.push('Агенты Мультики (задачи, созданные за неделю):');
  for (const a of week.agents) {
    const statuses = Object.entries(a.statuses).map(([k, v]) => `${k} ${v}`).join(', ') || '—';
    lines.push(`- ${a.name}: запусков ${a.runs} (${statuses})${a.tasks.length ? '; ' + a.tasks.map((t) => t.identifier).join(', ') : ''}`);
  }
  return lines.join('\n') + '\n';
}

// ── CLI ────────────────────────────────────────────────────────────────────────────────────

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const m = /^--([a-z-]+)$/.exec(argv[i]);
    if (!m) throw new Error(`unexpected argument ${argv[i]}`);
    out[m[1]] = argv[i + 1];
  }
  return out;
}

function multica(...argv) {
  return JSON.parse(execFileSync('multica', [...argv, '--output', 'json'], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, timeout: 60_000 }));
}

function writeAtomic(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp-${process.pid}`;
  writeFileSync(tmp, text);
  renameSync(tmp, path);
}

async function main() {
  const a = args(process.argv.slice(2));
  for (const need of ['stats-dir', 'state', 'out', 'md']) if (!a[need]) throw new Error(`--${need} is required`);
  const now = a.now ?? new Date().toISOString();
  const stats = {};
  for (const f of readdirSync(a['stats-dir']).filter((n) => n.endsWith('.json'))) {
    stats[f.slice(0, -5)] = JSON.parse(readFileSync(join(a['stats-dir'], f), 'utf8'));
  }
  if (!Object.keys(stats).length) throw new Error('no hub stats downloaded');
  const agentList = multica('agent', 'list');
  const agents = (Array.isArray(agentList) ? agentList : agentList.agents ?? []).map((x) => ({ id: x.id, name: x.name }));
  const issues = [];
  const from = Date.parse(now) - WEEK_MS;
  for (let offset = 0; offset < 1000; offset += 100) {
    const page = multica('issue', 'list', '--sort', 'created_at', '--direction', 'desc', '--limit', '100', '--offset', String(offset));
    const rows = page.issues ?? [];
    issues.push(...rows);
    if (!page.has_more || !rows.length || Date.parse(rows.at(-1).created_at) < from) break;
  }
  const commentsByIssue = {};
  for (const issue of issues) {
    if (Date.parse(issue.created_at) < from || issue.assignee_type !== 'agent') continue;
    const comments = multica('issue', 'comment', 'list', issue.id);
    commentsByIssue[issue.id] = Array.isArray(comments) ? comments : comments.comments ?? [];
  }
  const state = existsSync(a.state) ? JSON.parse(readFileSync(a.state, 'utf8')) : null;
  const { week, state: next } = collect({ agents, issues, commentsByIssue, stats, state, now });
  writeAtomic(a.out, JSON.stringify(week, null, 2) + '\n');
  writeAtomic(a.md, factsMarkdown(week));
  writeAtomic(a.state, JSON.stringify(next) + '\n');
  process.stdout.write(JSON.stringify({ firstSnapshot: week.firstSnapshot, hubs: week.hubs.length, runs: week.agents.reduce((n, x) => n + x.runs, 0) }) + '\n');
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  main().catch((err) => {
    process.stderr.write(`weekly facts failed: ${err?.message ?? err}\n`);
    process.exit(1);
  });
}
