// Read-only reproduction against the committed pre-fix page, with no live requests.
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../..');
const baselineCommit = 'cbb84563d008d8c3c9b354511700537f27e9895d';
const html = execFileSync('git', ['show', `${baselineCommit}:aimarket-hub/terminal-home.html`], {cwd: root, encoding: 'utf8'});
const poll = html.match(/  async function poll\(\) \{[\s\S]*?\n  \}\n\n  \/\/ Live stats/)[0].split('\n\n  // Live stats')[0];
let renders = 0, live = false, peerCalls = 0;
const noop = () => {};
const context = {
  HUB: 'https://hub.test',
  fetch: async () => ({ok: true, json: async () => ({events: [{id: 2, purpose: 'feed'}], summary: {total_invocations: 2}})}),
  events: [{id: 1}], lastInv: 1, sparkInv: [], sparkRev: [],
  document: {getElementById: () => ({textContent: '1'})},
  setConn: ok => { live = ok; }, t: key => key, anim: noop, usd: noop, spark: noop,
  ensurePeers: () => { peerCalls++; return new Promise(() => {}); },
  renderFeed: () => { renders++; }, renderTicker: noop, renderTop: noop, renderPulse: noop, renderFed: noop,
};
vm.createContext(context);
vm.runInContext(poll + '; poll()', context);
setImmediate(() => {
  const result = {
    baselineCommit,
    scenario: 'Stats delivered a new feed event while the optional peers request never settled.',
    newEventsInMemory: context.events[0].id,
    liveBadge: live,
    renderFeedCalls: renders,
    pendingPeerRequests: peerCalls,
    freezeReproduced: context.events[0].id === 2 && live && renders === 0,
    incidentAttribution: 'Reproduced code defect; the actual user session/network state was unavailable, so this does not establish the cause of that session.',
  };
  console.log(JSON.stringify(result, null, 2));
  if (!result.freezeReproduced) process.exitCode = 1;
});
