// node --test multica/weekly-post/collect.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { collect, factsMarkdown } from './collect.mjs';

const NOW = '2026-11-09T11:00:00Z';
const agents = [{ id: 'a-vzhik', name: 'вжик' }, { id: 'a-shop', name: 'тайный покупатель' }];
const stats = (total, ext, self, vol) => ({ summary: { total_invocations: total, external_invocations: ext, operator_self_invocations: self,
  successful_invocations: total - 1, failed_invocations: 1, volume_total_usd: vol, capabilities_count: 282, peers_count: 22, invocations_24h: 5 } });

const issues = [
  { id: 'i1', identifier: 'MY-60', title: 'GitHub-сводка', status: 'done', assignee_type: 'agent', assignee_id: 'a-vzhik', created_at: '2026-11-05T08:00:00Z' },
  { id: 'i2', identifier: 'MY-61', title: 'Тайный покупатель', status: 'in_review', assignee_type: 'agent', assignee_id: 'a-shop', created_at: '2026-11-05T09:00:00Z' },
  { id: 'i3', identifier: 'MY-40', title: 'old', status: 'done', assignee_type: 'agent', assignee_id: 'a-vzhik', created_at: '2026-10-20T08:00:00Z' },
  { id: 'i4', identifier: 'MY-62', title: 'by a person', status: 'todo', assignee_type: 'member', assignee_id: 'u1', created_at: '2026-11-06T08:00:00Z' },
];
const commentsByIssue = {
  i1: [{ author_type: 'agent', author_id: 'a-vzhik', created_at: '2026-11-05T08:02:00Z', content: 'first' },
       { author_type: 'member', author_id: 'u1', created_at: '2026-11-05T08:03:00Z', content: 'thanks' },
       { author_type: 'agent', author_id: 'a-vzhik', created_at: '2026-11-05T08:04:00Z', content: 'final digest' }],
  i2: [{ author_type: 'agent', author_id: 'a-shop', created_at: '2026-11-05T09:03:00Z', content: 'x'.repeat(3000) }],
};

test('first week: snapshot, no deltas; agents count only their tasks in the window', () => {
  const { week, state } = collect({ agents, issues, commentsByIssue, stats: { 'modelmarket.dev': stats(100, 10, 90, 1.5) }, state: null, now: NOW });
  assert.equal(week.firstSnapshot, true);
  assert.equal(week.hubs[0].delta, null);
  const [vzhik, shop] = week.agents;
  assert.equal(vzhik.runs, 1);
  assert.equal(vzhik.tasks[0].answer, 'final digest', 'the last answer by the assignee, not a person’s reply');
  assert.equal(shop.tasks[0].answer.length < 1600, true, 'long answers are clipped');
  assert.deepEqual(shop.statuses, { in_review: 1 });
  assert.equal(state.hubs['modelmarket.dev'].counters.total_invocations, 100);
  assert.match(factsMarkdown(week), /первый снимок/);
});

test('next week: deltas against the snapshot', () => {
  const first = collect({ agents, issues, commentsByIssue, stats: { 'modelmarket.dev': stats(100, 10, 90, 1.5) }, state: null, now: NOW });
  const { week } = collect({ agents, issues: [], commentsByIssue: {}, stats: { 'modelmarket.dev': stats(160, 14, 146, 1.9) }, state: first.state, now: '2026-11-16T11:00:00Z' });
  const d = week.hubs[0].delta;
  assert.deepEqual([d.total_invocations, d.external_invocations, d.operator_self_invocations, d.volume_total_usd], [60, 4, 56, 0.4]);
  assert.equal(week.hubs[0].since, '2026-11-09T11:00:00.000Z');
  const md = factsMarkdown(week);
  assert.match(md, /с 2026-11-09 вызовов 60 \(внешних 4, своих 56\)/);
  assert.match(md, /вжик: запусков 0/);
});
