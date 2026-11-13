import assert from "node:assert/strict";

const hub = "https://modelmarket.dev";
const prefix = "/ai-market/v2";
const expected = {
  coinmarketcap: { name: "CoinMarketCap", method: "GET", price: 0.01, basis: "per_request",
    endpoint: "https://pro-api.coinmarketcap.com/x402/v3/cryptocurrency/quotes/latest", host: "coinmarketcap.com" },
  tavily: { name: "Tavily", method: "POST", price: 0.01, basis: "per_request",
    endpoint: "https://x402.tavily.com/search", host: "docs.tavily.com" },
  laso: { name: "Laso", method: "GET", price: 5, basis: "minimum_load",
    endpoint: "https://laso.finance/get-card", host: "docs.laso.finance" },
};

async function get(path, status = 200) {
  const response = await fetch(new URL(path, hub), { headers: { "cache-control": "no-cache" },
    signal: AbortSignal.timeout(20_000) });
  assert.equal(response.status, status, path);
  return response.headers.get("content-type")?.includes("json") ? response.json() : response.text();
}

const [home, directory, health, manifest, observed, bridge, locales, cmc, tavily, laso, limited, local] = await Promise.all([
  get("/"), get(`${prefix}/external-services`), get(`${prefix}/health`), get(`${prefix}/manifest`),
  get(`${prefix}/federation/observed-sellers`), get(`${prefix}/x402-bridge`), get("/hub-ui-i18n.json"),
  ...["CMC", "web search", "prepaid card"].map((intent) => get(`${prefix}/search?${new URLSearchParams({ intent })}`)),
  get(`${prefix}/search?intent=Laso&budget=0.05`), get(`${prefix}/search?intent=CMC&hub=local`),
  get(`${prefix}/account/withdrawals`, 401),
]);
assert(home.includes('id="external-directory"') && home.includes('class="apex-tools"'));
assert.equal(health.status, "ok");
assert.deepEqual(directory.external.map((row) => row.id), Object.keys(expected));
for (const item of directory.external) {
  const spec = expected[item.id];
  assert.deepEqual([item.name, item.method, item.published_price_usd, item.price_basis, item.endpoint,
    new URL(item.documentation_url).hostname], [spec.name, spec.method, spec.price, spec.basis, spec.endpoint, spec.host]);
  assert.equal(item.hub_invoke, false);
  assert.equal(item.payment_recipient, "provider");
  assert.equal(item.payment_protocol, "x402");
  assert.equal(item.asset, "USDC");
}
const ids = (data) => data.external.map((row) => row.id);
assert.deepEqual([ids(cmc), ids(tavily), ids(laso), ids(limited), ids(local)],
  [["coinmarketcap"], ["tavily"], ["laso"], [], []]);
assert(!("external" in manifest));
for (const entry of [...manifest.tools, ...cmc.matches, ...tavily.matches, ...laso.matches]) {
  assert(!Object.hasOwn(expected, entry.id ?? entry.capability_id ?? ""));
}
const observedCounts = Object.fromEntries(observed.sellers.map((row) => [row.origin, row.routes_served]));
assert(!directory.external.some((row) => new URL(row.endpoint).origin in observedCounts));
assert.equal(bridge.balance_usd, 0);
assert.equal(bridge.limits.per_call_usd, 0.05);
assert.equal(bridge.limits.per_seller_day_usd, 0.5);
const languages = ["en", "ru", "es", "fr", "zh"];
for (const lang of languages) assert(locales.ui[lang].external_title && locales.ui[lang].external_note);
console.log(JSON.stringify({ checked_at_utc: new Date().toISOString(), health: health.status,
  providers: ids(directory), searches: [ids(cmc), ids(tavily), ids(laso)], budget_and_local_filters: true,
  prior_apex_cta: true, languages, manifest_count: manifest.total_capabilities,
  external_rows_in_manifest_or_matches: 0, observedCounts, bridge: { enabled: bridge.enabled,
    balance_usd: bridge.balance_usd, limits: bridge.limits }, unauthenticated_withdrawals: 401 }, null, 2));
