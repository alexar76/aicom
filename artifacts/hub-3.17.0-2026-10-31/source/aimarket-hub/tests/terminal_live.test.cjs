// Execute the page's real request/poll functions with a controlled network and clock.
// No browser, packages, live calls or gameplay data are needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const page = fs.readFileSync(path.join(__dirname, '..', 'terminal-home.html'), 'utf8');
function section(start, end) {
  const from = page.indexOf(start);
  const to = page.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `missing page section: ${start}`);
  return page.slice(from, to);
}
const source = [
  ...['POLL', 'LIVE_TIMEOUT_MS', 'LIVE_STALE_MS'].map(name => page.match(new RegExp(`const ${name} = [^;]+;`))[0]),
  page.match(/let pollInFlight = [^;]+;/)[0],
  page.match(/let peersRequest = [^;]+;/)[0],
  section('  async function fetchJson(', '\n  // Resolved against'),
  section('  async function ensurePeers()', '\n  async function fetchPreview'),
  section('  /* Poll live stats */', '\n  // Live stats must not'),
].join('\n');
const flush = () => new Promise(resolve => setImmediate(resolve));

function fixture() {
  let now = 1_000_000, sequence = 0;
  const timers = new Map(), nodes = new Map(), listeners = new Map();
  const calls = {stats: 0, peers: 0}, painted = [], connections = [];
  const never = signal => new Promise((_, reject) => {
    signal.addEventListener('abort', () => reject(new Error('aborted')), {once: true});
  });
  let stats = async () => ({events: [{id: 2, purpose: 'feed'}], summary: {total_invocations: 2}});
  let peers = never;
  let renderFailure = false;
  const noop = () => {};
  const context = {
    HUB: 'https://hub.test', AbortController,
    Date: class extends Date { static now() { return now; } },
    setTimeout(fn, ms) { const id = ++sequence; timers.set(id, {at: now + ms, fn}); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch: async (url, options) => {
      const peer = url.endsWith('/federation/peers');
      calls[peer ? 'peers' : 'stats']++;
      const answer = await (peer ? peers : stats)(options.signal);
      return {ok: true, json: async () => answer};
    },
    events: [{id: 1}], lastInv: 1, lastSummary: {}, sparkInv: [], sparkRev: [],
    peersCache: null, pendingCache: [], peersForFed: null,
    document: {
      visibilityState: 'visible',
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, {textContent: '1'});
        return nodes.get(id);
      },
      addEventListener(name, fn) { listeners.set(name, fn); },
    },
    addEventListener(name, fn) { listeners.set(name, fn); },
    setConn(ok, label) { connections.push({ok, label}); },
    t: key => key, anim: noop, usd: noop, spark: noop,
    renderFeed() {
      if (renderFailure) throw new Error('render failed');
      painted.push(context.events[0]?.id);
    },
    renderTicker: noop, renderTop: noop, renderPulse: noop, renderFed: noop, renderKnockRail: noop,
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return {
    context, calls, painted, connections, listeners, timers,
    poll: () => context.poll(),
    stats(fn) { stats = fn; }, peers(fn) { peers = fn; },
    failRender(value) { renderFailure = value; },
    never,
    async advance(ms) {
      now += ms;
      for (const [id, timer] of [...timers]) {
        if (timer.at <= now) { timers.delete(id); timer.fn(); }
      }
      await flush();
    },
  };
}

test('a hanging peer request never holds new feeds or their Live status', async () => {
  const f = fixture();
  await f.poll();
  assert.deepEqual(f.painted, [2]);
  assert.equal(f.connections.at(-1).ok, true);
  assert.equal(f.calls.peers, 1);
  await f.poll();
  assert.equal(f.calls.stats, 2);
  assert.equal(f.calls.peers, 1, 'peer requests must be shared');
  await f.advance(10_001);
  await f.poll();
  assert.equal(f.calls.peers, 2, 'a timed-out peer request must release its retry slot');
});

test('a stalled stats request times out, prevents overlap and then recovers', async () => {
  const f = fixture();
  f.stats(f.never);
  const first = f.poll();
  await f.poll();
  await f.poll();
  assert.equal(f.calls.stats, 1);
  await f.advance(10_001);
  await first;
  assert.equal(f.connections.at(-1).ok, false);
  assert.deepEqual(f.painted, []);
  f.stats(async () => ({events: [{id: 3, purpose: 'scan'}], summary: {total_invocations: 3}}));
  await f.poll();
  assert.deepEqual(f.painted, [3]);
  assert.equal(f.connections.at(-1).ok, true);
});

test('the request deadline also covers a stalled JSON body', async () => {
  const f = fixture();
  f.context.fetch = async (_url, options) => ({ok: true, json: () => f.never(options.signal)});
  const pending = f.poll();
  await flush();
  await f.advance(10_001);
  await pending;
  assert.deepEqual(f.painted, []);
  assert.equal(f.connections.at(-1).ok, false);
});

test('a peer JSON body also times out and releases its retry slot', async () => {
  const f = fixture();
  let calls = 0;
  f.context.fetch = async (_url, options) => {
    calls++;
    return {ok: true, json: () => f.never(options.signal)};
  };
  const first = f.context.ensurePeers();
  const rejected = assert.rejects(first, /aborted/);
  await flush();
  await f.advance(10_001);
  await rejected;
  f.context.fetch = async () => { calls++; return {ok: true, json: async () => ({peers: []})}; };
  await f.context.ensurePeers();
  assert.equal(calls, 2);
});

test('a Live badge expires even when browser suspension delays request deadlines', async () => {
  const f = fixture();
  await f.poll();
  await f.advance(15_001);
  f.context.checkLiveFreshness();
  assert.equal(f.connections.at(-1).ok, false);
});

test('online, restored pages and visible tabs immediately retry; hidden tabs do not', async () => {
  const f = fixture();
  for (const event of ['online', 'pageshow', 'visibilitychange']) {
    f.listeners.get(event)();
    await flush();
  }
  assert.equal(f.calls.stats, 3);
  f.context.document.visibilityState = 'hidden';
  f.listeners.get('visibilitychange')();
  await flush();
  assert.equal(f.calls.stats, 3);
  f.listeners.get('offline')();
  assert.equal(f.connections.at(-1).ok, false);
});

test('a render failure cannot claim Live and does not block the next update', async () => {
  const f = fixture();
  f.failRender(true);
  await f.poll();
  assert.equal(f.connections.some(c => c.ok), false);
  f.failRender(false);
  await f.poll();
  assert.deepEqual(f.painted, [2]);
  assert.equal(f.connections.at(-1).ok, true);
});

test('malformed stats preserve the last rendered event and show reconnection', async () => {
  const f = fixture();
  await f.poll();
  f.stats(async () => ({events: {id: 999}, summary: {}}));
  await f.poll();
  assert.deepEqual(f.painted, [2]);
  assert.equal(f.context.events[0].id, 2);
  assert.equal(f.connections.at(-1).ok, false);
});
