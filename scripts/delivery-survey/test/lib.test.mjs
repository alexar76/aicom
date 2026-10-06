import assert from "node:assert/strict";
import { test } from "node:test";
import {
  USDC_BASE, atomicToUsd, buildRequest, classify, eligibility, guardedRequest, isPublicAddress, judgeOffer, read402,
  sample, terms, usdToAtomic, usdcOffer,
} from "../lib.mjs";

const CAP = 10_000n;   // $0.01
const SELLER = "0x00000000000000000000000000000000000000a1";

const offer = (over = {}) => ({
  scheme: "exact", network: "eip155:8453", asset: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  amount: "5000", payTo: SELLER, maxTimeoutSeconds: 60, extra: { name: "USD Coin", version: "2" }, ...over,
});

const listing = (resource, over = {}) => ({
  x402Version: 2,
  resource,
  accepts: [offer()],
  extensions: { bazaar: { info: { input: { type: "http", method: "GET", queryParams: { q: "eth" } } } } },
  quality: { l30DaysUniquePayers: 1 },
  ...over,
});

test("dollars and USDC atomic units convert both ways", () => {
  assert.equal(usdToAtomic("0.01"), 10_000n);
  assert.equal(usdToAtomic("$1.5"), 1_500_000n);
  assert.equal(usdToAtomic("0.000001"), 1n);
  assert.throws(() => usdToAtomic("0.0000001"));
  assert.throws(() => usdToAtomic("-1"));
  assert.equal(atomicToUsd(3000n), "0.003");
  assert.equal(atomicToUsd(10_000n), "0.01");
});

test("only an exact Base USDC offer to a real payee within the cap is taken", () => {
  assert.equal(usdcOffer([offer()], CAP).amount, "5000");
  assert.equal(usdcOffer([offer({ network: "base" })], CAP).network, "base");
  assert.equal(usdcOffer([offer({ amount: undefined, maxAmountRequired: "7000" })], CAP).maxAmountRequired, "7000");
  assert.equal(usdcOffer([offer({ amount: "10001" })], CAP), null);
  assert.equal(usdcOffer([offer({ amount: "0" })], CAP), null);
  assert.equal(usdcOffer([offer({ scheme: "upto" })], CAP), null);
  assert.equal(usdcOffer([offer({ network: "eip155:84532" })], CAP), null);
  assert.equal(usdcOffer([offer({ asset: "0x036CbD53842c5426634e7929541eC2318f3dCF7e" })], CAP), null);
  assert.equal(usdcOffer([offer({ payTo: "not-an-address" })], CAP), null);
  assert.equal(usdcOffer([offer({ amount: "99999" }), offer({ amount: "2000" })], CAP).amount, "2000");
});

test("eligibility names every reason a listing is left out", () => {
  assert.equal(eligibility(listing("https://api.example.com/x"), CAP), "ok");
  assert.equal(eligibility(listing("https://api.example.com/x", { x402Version: 1 }), CAP), "not_x402_v2");
  assert.equal(eligibility(listing("http://api.example.com/x"), CAP), "not_https");
  assert.equal(eligibility(listing("https://203.0.113.9/x"), CAP), "ip_address_host");
  assert.equal(eligibility(listing("https://modelmarket.dev/x402/x402-check"), CAP), "own_host");
  assert.equal(eligibility(listing("https://hub.attestedmemory.net/x"), CAP), "own_host");
  assert.equal(eligibility(listing("https://notmodelmarket.dev/x"), CAP), "ok");
  assert.equal(eligibility(listing("https://api.example.com/x", { extensions: {} }), CAP), "no_declared_input");
  assert.equal(eligibility(listing("https://api.example.com/x", { accepts: [offer({ amount: "50000" })] }), CAP), "no_base_usdc_offer_within_cap");
  assert.equal(eligibility(listing("https://api.example.com/x", { accepts: [offer({ payTo: "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a" })] }), CAP), "own_wallet");
});

test("the sample is one listing per host, seeded and reproducible, and accounts for every listing", () => {
  const items = [];
  for (let h = 0; h < 30; h++) for (let k = 0; k < 3; k++) items.push(listing(`https://seller${h}.example.com/r${k}`));
  items.push(listing("https://modelmarket.dev/x402/mcp-diff"), listing("http://plain.example.com/x"));
  const a = sample(items, { hosts: 10, cap: CAP, seed: "s1" });
  const b = sample(items, { hosts: 10, cap: CAP, seed: "s1" });
  const c = sample(items, { hosts: 10, cap: CAP, seed: "s2" });
  assert.deepEqual(a, b);
  assert.notDeepEqual(a.entries.map((e) => e.host), c.entries.map((e) => e.host));
  assert.equal(a.entries.length, 10);
  assert.equal(new Set(a.entries.map((e) => e.host)).size, 10);
  assert.equal(a.meta.eligible_hosts, 30);
  assert.deepEqual(a.meta.excluded, { ok: 90, own_host: 1, not_https: 1 });
  assert.equal(Object.values(a.meta.excluded).reduce((x, y) => x + y, 0), items.length);
  assert.equal(a.entries[0].listed.payTo, SELLER);
  assert.equal(a.entries[0].listings_at_host, 3);
});

test("the seller's example becomes the request: query, JSON body, path parameters", () => {
  const get = buildRequest({ resource: "https://api.example.com/price?chain=base", input: { method: "GET", queryParams: { symbol: "ETH", n: 3 } } });
  assert.equal(get.method, "GET");
  assert.equal(get.url, "https://api.example.com/price?chain=base&symbol=ETH&n=3");
  assert.equal(get.body, null);

  const post = buildRequest({ resource: "https://api.example.com/search", input: { method: "POST", bodyType: "json", body: { query: "x", k: [1] } } });
  assert.equal(post.body, '{"query":"x","k":[1]}');
  assert.equal(post.headers["content-type"], "application/json");

  const bare = buildRequest({ resource: "https://api.example.com/run", input: { method: "POST" } });
  assert.equal(bare.body, "{}");

  const path = buildRequest({ resource: "https://api.onesource.io/api/chain/ens/:input", input: { method: "GET", pathParams: { input: "vitalik.eth" } } });
  assert.equal(path.url, "https://api.onesource.io/api/chain/ens/vitalik.eth");

  const form = buildRequest({ resource: "https://api.example.com/f", input: { method: "POST", bodyType: "form-data", body: { a: "1 2" } } });
  assert.equal(form.body, "a=1+2");
  assert.equal(form.headers["content-type"], "application/x-www-form-urlencoded");
});

test("a request is refused when the example cannot be sent as declared", () => {
  assert.equal(buildRequest({ resource: "https://a.example.com/x/:id", input: { method: "GET" } }).error, "path_parameter_without_example");
  assert.equal(buildRequest({ resource: "https://a.example.com/x", input: { method: "GET", queryParams: { q: { type: "string", description: "query" } } } }).error, "example_has_no_values");
  assert.equal(buildRequest({ resource: "https://a.example.com/x", input: { method: "DELETE" } }).error, "method_not_supported");
  assert.equal(buildRequest({ resource: "https://a.example.com/x", input: { method: "POST", bodyType: "binary", body: "AAAA" } }).error, "body_type_not_supported");
  assert.equal(buildRequest({ resource: "https://a.example.com/x", input: { method: "POST", body: { blob: "x".repeat(70_000) } } }).error, "example_too_large");
});

test("declared headers are listed, never sent", () => {
  const r = buildRequest({ resource: "https://a.example.com/x", input: { method: "GET", headers: { "x-api-key": "rwk_..." } } });
  assert.deepEqual(r.declared_headers, ["x-api-key"]);
  assert.equal(r.headers["x-api-key"], undefined);
});

test("only public unicast addresses pass", () => {
  for (const ip of ["10.1.2.3", "127.0.0.1", "169.254.169.254", "100.64.0.1", "172.16.5.4", "192.168.1.1", "192.0.2.10",
    "198.18.0.1", "198.51.100.7", "203.0.113.1", "224.0.0.1", "0.0.0.0", "255.255.255.255",
    "::", "::1", "fe80::1", "fc00::1", "fd12:3456::1", "::ffff:10.0.0.1", "::ffff:8.8.8.8", "64:ff9b::a00:1",
    "2002:a00:1::1", "2001:db8::1", "ff02::1", "not-an-ip"]) {
    assert.equal(isPublicAddress(ip), false, ip);
  }
  for (const ip of ["8.8.8.8", "1.1.1.1", "104.16.0.1", "2606:4700:4700::1111", "2a00:1450:4001::200e"]) {
    assert.equal(isPublicAddress(ip), true, ip);
  }
});

test("the transport refuses non-public literals and plain HTTP before connecting", async () => {
  assert.equal((await guardedRequest({ method: "GET", url: "https://127.0.0.1/x", headers: {} }, { userAgent: "t" })).error, "non_public_address");
  assert.equal((await guardedRequest({ method: "GET", url: "https://[::1]/x", headers: {} }, { userAgent: "t" })).error, "non_public_address");
  assert.equal((await guardedRequest({ method: "GET", url: "http://api.example.com/x", headers: {} }, { userAgent: "t" })).error, "not_https");
  const refusing = (host, opts, cb) => cb(Object.assign(new Error("private"), { code: "ENOTPUBLIC" }));
  assert.equal((await guardedRequest({ method: "GET", url: "https://rebind.example.com/x", headers: {} }, { userAgent: "t", lookup: refusing })).error, "non_public_address");
});

const v2header = (accepts) => Buffer.from(JSON.stringify({ x402Version: 2, resource: { url: "https://a.example.com/x" }, accepts })).toString("base64");

test("a 402 is read like the reference client reads it: v2 header, v1 body", () => {
  const v2 = read402({ headers: { "payment-required": v2header([offer()]) }, body: Buffer.from("") });
  assert.equal(v2.ok, true);
  assert.equal(v2.required.x402Version, 2);
  const v1 = read402({ headers: {}, body: Buffer.from(JSON.stringify({ x402Version: 1, accepts: [offer({ network: "base" })] })) });
  assert.equal(v1.ok, true);
  assert.equal(read402({ headers: {}, body: Buffer.from('{"error":"pay me"}') }).ok, false);
});

test("the live offer is judged against the listing", () => {
  const listed = terms(offer());
  assert.equal(judgeOffer(listed, { accepts: [offer()] }, CAP).verdict, "payable");
  assert.equal(judgeOffer(listed, { accepts: [offer({ amount: "6000" })] }, CAP).verdict, "payable_price_changed");
  assert.equal(judgeOffer(listed, { accepts: [offer({ payTo: "0x00000000000000000000000000000000000000b2" })] }, CAP).verdict, "payee_changed");
  assert.equal(judgeOffer(listed, { accepts: [offer({ amount: "20000" })] }, CAP).verdict, "over_cap");
  assert.equal(judgeOffer(listed, { accepts: [offer({ extra: { name: "USDC", version: "2" } })] }, CAP).verdict, "wrong_usdc_domain");
  assert.equal(judgeOffer(listed, { accepts: [offer({ extra: {} })] }, CAP).verdict, "no_usdc_domain");
  assert.equal(judgeOffer(listed, { accepts: [offer({ asset: "0x0000000000000000000000000000000000000001" })] }, CAP).verdict, "no_base_usdc_offer");
  assert.equal(judgeOffer(listed, { accepts: [offer({ payTo: SELLER.toUpperCase().replace("0X", "0x") })] }, CAP).verdict, "payable");
});

test("what came back is named: open, rejected example, redirect, gone, error", () => {
  const entry = { resource: "https://a.example.com/x", listed: terms(offer()) };
  const req = { method: "GET", url: entry.resource };
  assert.equal(classify(entry, req, { status: 200, headers: {}, body: Buffer.from("{}") }, CAP).verdict, "open_without_payment");
  assert.equal(classify(entry, req, { status: 422, headers: {} }, CAP).verdict, "rejects_its_own_example");
  assert.deepEqual(classify(entry, req, { status: 302, headers: { location: "https://elsewhere.example.net/y" } }, CAP),
    { verdict: "redirects", location_host: "elsewhere.example.net" });
  assert.equal(classify(entry, req, { status: 404, headers: {} }, CAP).verdict, "gone");
  assert.equal(classify(entry, req, { error: "timeout" }, CAP).verdict, "timeout");
  assert.equal(classify(entry, { error: "method_not_supported" }, {}, CAP).verdict, "method_not_supported");
  const paid = classify(entry, req, { status: 402, headers: { "payment-required": v2header([offer()]) }, body: Buffer.from("") }, CAP);
  assert.equal(paid.verdict, "payable");
  assert.equal(paid.x402_version, 2);
  assert.equal(USDC_BASE, offer().asset.toLowerCase());
});

test("a seller can check itself: --host takes every eligible listing of that host, nothing else", () => {
  const items = [listing("https://me.example.com/a"), listing("https://me.example.com/b"), listing("https://other.example.com/a"),
    listing("http://me.example.com/plain")];
  const plan = sample(items, { hosts: 100, cap: CAP, seed: "s", only: new Set(["me.example.com"]) });
  assert.deepEqual(plan.entries.map((e) => e.resource).sort(), ["https://me.example.com/a", "https://me.example.com/b"]);
  assert.deepEqual(plan.meta.only_hosts, ["me.example.com"]);
  assert.deepEqual(plan.meta.excluded, { ok: 2, not_https: 1 });
});
