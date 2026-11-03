const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const page = fs.readFileSync(path.join(__dirname, '..', 'terminal-home.html'), 'utf8');
const ui = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'hub-ui-i18n.json'))).ui;
function section(start, end) {
  const from = page.indexOf(start), to = page.indexOf(end, from);
  assert.ok(from >= 0 && to > from);
  return page.slice(from, to);
}
function fixture() {
  const listeners = {};
  const ctx = {
    URL, Date, lang: 'en', HUB: 'https://hub.example',
    input: {value: 'weather'},
    drop: {innerHTML: '', classList: {add() {}}},
    form: {addEventListener(name, callback) { listeners[name] = callback; }},
    t(key) { return ui[ctx.lang][key] || key; },
    hostOf: u => u === 'local' ? '' : new URL(u).host,
    descForSearch: c => c.description || '',
    capabilityPrice: c => String(c.price_per_call_usd),
    accessMode: c => c.access_mode || 'public',
    usd: n => '$' + n,
    fetch: async () => ({json: async () => ctx.response}),
  };
  vm.createContext(ctx);
  vm.runInContext(section('  function esc(', '\n  function visitorId('), ctx);
  vm.runInContext(section('  let searchMatches = []', '\n  function showInvoke('), ctx);
  vm.runInContext(section("  form.addEventListener('submit',", "\n  document.querySelectorAll('.intent-example')"), ctx);
  return {
    ctx,
    render(matches, observed) { ctx.renderSearchResults(matches, {}, observed); return ctx.drop.innerHTML; },
    async search(response) { ctx.response = response; await listeners.submit({preventDefault() {}}); return ctx.drop.innerHTML; },
    matches() { return vm.runInContext('searchMatches', ctx); },
    relanguage(lang) {
      ctx.lang = lang;
      vm.runInContext('renderSearchResults(searchMatches, searchMetaState, searchObserved)', ctx);
      return ctx.drop.innerHTML;
    },
  };
}
const quote = {
  seller: 'https://seller.example', seller_name: 'Weather seller',
  url: 'https://seller.example/weather', method: 'POST', description: 'Weather',
  price_usd: 0.003, pay_to: '0x123', network: 'eip155:8453',
  observed_by: 'https://hub.example', observed_at: '2026-10-31T10:00:00Z',
};
const catalog = {name: 'Weather catalog', source_hub: 'https://catalog.example', description: 'weather'};

test('observed-only search is a result, never a sandbox invocation', async () => {
  const f = fixture();
  const html = await f.search({matches: [], observed: [quote]});
  assert.match(html, /Observed offers/);
  assert.doesNotMatch(html, /data-idx|click to try free/);
  assert.ok(!html.includes(ui.en.no_matches));
  assert.ok(!html.includes(ui.en.search_exact_fallback));
  assert.equal(f.matches().length, 0);
  assert.match(html, /href="https:\/\/seller.example\/weather"/);
  assert.match(html, /noopener noreferrer/);
  assert.match(html, /Seller did not sign this listing/);
  assert.match(html, /2026-10-31 10:00:00 UTC/);
});

test('catalog indexes remain correct with filtered and observed results', () => {
  const f = fixture();
  const html = f.render([{...catalog, access_mode: 'operator_gated'}, catalog], [quote]);
  assert.equal(f.matches().length, 1);
  assert.match(html, /data-idx="0"/);
  assert.doesNotMatch(html, /data-idx="1"/);
  assert.ok(html.indexOf('Catalogue offers') < html.indexOf('Observed offers'));
});

test('only recorded catalogue verification produces a signed badge', () => {
  const f = fixture();
  let html = f.render([{...catalog, provider_pubkey: 'key', trust_score: 1}], []);
  assert.match(html, /verification not recorded/);
  assert.ok(!html.includes(ui.en.evidence_signed));
  html = f.render([{...catalog, evidence: {
    kind: 'signed_catalogue', scope: 'catalogue', signer: 'https://catalog.example',
    signer_public_key: 'a-public-key-from-the-verification', checked_at: '2026-10-30T09:00:00Z',
    checked_by: 'https://hub.example',
  }}], []);
  assert.ok(html.includes(ui.en.evidence_signed));
  assert.match(html, /https:\/\/catalog.example/);
  assert.match(html, /2026-10-30 09:00:00 UTC/);
  assert.match(html, /title="a-public-key-from-the-verification"/);
});

test('observed offers cannot promote their own metadata into a signed badge', () => {
  const f = fixture();
  const html = f.render([], [{...quote, evidence: {kind: 'signed_catalogue', scope: 'catalogue', signer_public_key: 'key', signer: 'x', checked_at: quote.observed_at}}]);
  assert.ok(!html.includes(ui.en.evidence_signed));
});

test('seller text is escaped and unsafe endpoint links are omitted', () => {
  const f = fixture();
  for (const url of ['javascript:alert(1)', 'https://other.example/pay', 'https://name:password@seller.example/pay']) {
    const html = f.render([], [{...quote, url, seller_name: '<img src=x onerror=alert(1)>', observed_by: '<script>alert(1)</script>'}]);
    assert.doesNotMatch(html, /<script>|<img|class="search-seller-link"/);
    assert.match(html, /&lt;img/);
  }
});

test('language changes preserve observed-only results in all five languages', () => {
  const f = fixture(); f.render([], [quote]);
  for (const lang of Object.keys(ui)) {
    const html = f.relanguage(lang);
    assert.ok(html.includes(ui[lang].search_observed));
    assert.ok(html.includes(ui[lang].evidence_unsigned));
    assert.ok(html.includes('https://seller.example/weather'));
  }
});

test('empty search resets prior results and missing timestamps stay unknown', async () => {
  const f = fixture();
  const html = f.render([{...catalog, source_hub: 'local'}], [{...quote, observed_at: '<script>'}]);
  assert.ok(html.includes(ui.en.evidence_local));
  assert.ok(html.includes(ui.en.evidence_unknown));
  assert.doesNotMatch(html, /datetime="undefined|<script>/);
  const empty = await f.search({matches: [], observed: []});
  assert.ok(empty.includes(ui.en.no_matches));
  assert.equal(f.matches().length, 0);
});
