import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createApp } from "../src/app.js";
import { createReviewStore, reviewId } from "../src/web/review.js";

const TOKEN = "a".repeat(64);
const ADMIN = "admin-token-for-tests";
const SELLERS = { yutao: { token: TOKEN, name: "YuTao — Insight and PriorSeal" } };
const EXCERPT = "Insight answered 19 of 20 routes with a 402.\n\nPriorSeal: 4 of 4 listed.";

async function serve(opts = {}) {
  const store = opts.reviewStore ?? createReviewStore();
  const app = createApp({ publicUrl: "https://modelmarket.dev", reviewSellers: SELLERS, reviewAdminToken: ADMIN,
                          reviewStore: store, ...opts });
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  return { store, call: (path, init) => fetch(base + path, { redirect: "manual", ...init }),
           close: () => new Promise((r) => server.close(r)) };
}
const asAdmin = (body) => ({ method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${ADMIN}` },
                             body: JSON.stringify(body) });

test("the id is the gate's: sha256 of seller, newline, excerpt, first 20 hex digits", () => {
  // The same vector is in tests/test_seller_review.py: change both or neither.
  assert.equal(reviewId("yutao", "Insight: 19 of 20."), "927c321a8244292a36da");
});

test("only the gate's token files a passage, and filing twice is one request", async () => {
  const s = await serve();
  try {
    assert.equal((await s.call("/tools/review/api/requests", { ...asAdmin({}), headers: { "content-type": "application/json" } })).status, 401);
    const first = await s.call("/tools/review/api/requests", asAdmin({ seller: "yutao", excerpt: EXCERPT, title: "Draft", not_before: "2026-11-20T00:00:00Z" }));
    assert.equal(first.status, 201);
    const rec = await first.json();
    assert.equal(rec.id, reviewId("yutao", EXCERPT));
    assert.equal(rec.decision, null);
    const again = await s.call("/tools/review/api/requests", asAdmin({ seller: "yutao", excerpt: EXCERPT }));
    assert.equal(again.status, 200);
    assert.equal((await s.call("/tools/review/api/requests", asAdmin({ seller: "nobody", excerpt: EXCERPT }))).status, 400);
    assert.equal((await s.call("/tools/review/api/requests", asAdmin({ seller: "yutao", excerpt: " " }))).status, 400);
    const read = await s.call(`/tools/review/api/requests/${rec.id}`, { headers: { authorization: `Bearer ${ADMIN}` } });
    assert.equal((await read.json()).id, rec.id);
    assert.equal((await s.call(`/tools/review/api/requests/${rec.id}`)).status, 401);
  } finally { await s.close(); }
});

test("the seller reads the passage on a private page and in both feeds, and a wrong token sees nothing", async () => {
  const s = await serve();
  try {
    await s.call("/tools/review/api/requests", asAdmin({ seller: "yutao", excerpt: EXCERPT, title: "Draft <b>post</b>" }));
    const res = await s.call(`/tools/review/${TOKEN}/`);
    assert.equal(res.status, 200);
    assert.equal(res.headers.get("cache-control"), "no-store");
    assert.match(res.headers.get("x-robots-tag"), /noindex/);
    assert.equal(res.headers.get("referrer-policy"), "no-referrer");
    const body = await res.text();
    assert.match(body, /Insight answered 19 of 20 routes/);
    assert.match(body, /Draft &lt;b&gt;post&lt;\/b&gt;/);   // escaped, never markup
    assert.match(body, /name="decision" value="ok"/);
    const feed = await (await s.call(`/tools/review/${TOKEN}/feed.xml`)).text();
    assert.match(feed, /<feed xmlns="http:\/\/www.w3.org\/2005\/Atom">/);
    assert.match(feed, /PriorSeal: 4 of 4 listed/);
    const j = await (await s.call(`/tools/review/${TOKEN}/feed.json`)).json();
    assert.equal(j.requests.length, 1);
    assert.equal((await s.call(`/tools/review/${"b".repeat(64)}/`)).status, 404);
    assert.equal((await s.call("/tools/review/short/")).status, 404);
    assert.equal((await s.call(`/tools/review/${TOKEN}`)).status, 301);
  } finally { await s.close(); }
});

test("the seller answers with an ordinary form, can change the answer, and the gate reads it", async () => {
  const s = await serve();
  try {
    const rec = await (await s.call("/tools/review/api/requests", asAdmin({ seller: "yutao", excerpt: EXCERPT }))).json();
    const form = (decision, note) => ({ method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
                                        body: new URLSearchParams({ decision, note }).toString() });
    const objected = await s.call(`/tools/review/${TOKEN}/${rec.id}`, form("object", "PriorSeal is 3 of 4 now"));
    assert.equal(objected.status, 303);
    assert.equal(objected.headers.get("location"), `/tools/review/${TOKEN}/#r-${rec.id}`);
    let seen = await (await s.call(`/tools/review/api/requests/${rec.id}`, { headers: { authorization: `Bearer ${ADMIN}` } })).json();
    assert.equal(seen.decision, "object");
    assert.equal(seen.note, "PriorSeal is 3 of 4 now");
    await s.call(`/tools/review/${TOKEN}/${rec.id}`, form("ok", ""));
    seen = await (await s.call(`/tools/review/api/requests/${rec.id}`, { headers: { authorization: `Bearer ${ADMIN}` } })).json();
    assert.equal(seen.decision, "ok");
    assert.deepEqual(seen.history.map((h) => h.decision), ["object", "ok"]);
    assert.equal((await s.call(`/tools/review/${TOKEN}/${rec.id}`, form("maybe", ""))).status, 400);
    assert.equal((await s.call(`/tools/review/${"b".repeat(64)}/${rec.id}`, form("ok", ""))).status, 404);
  } finally { await s.close(); }
});

test("answers survive a restart, and a broken store is never overwritten", async () => {
  const dir = mkdtempSync(join(tmpdir(), "review-"));
  const file = join(dir, "state.json");
  const one = createReviewStore({ file });
  const { record } = one.create({ seller: "yutao", excerpt: EXCERPT });
  one.decide(record.id, "yutao", "ok", "fine");
  const two = createReviewStore({ file });
  assert.equal(two.get(record.id).decision, "ok");
  writeFileSync(file, "{not json");
  assert.throws(() => createReviewStore({ file }), /unreadable/);
  assert.equal(readFileSync(file, "utf8"), "{not json");
});

test("without the tokens nothing under /tools/review exists", async () => {
  const s = await serve({ reviewSellers: {}, reviewAdminToken: "" });
  try {
    assert.equal((await s.call(`/tools/review/${TOKEN}/`)).status, 404);
    assert.equal((await s.call("/tools/review/api/requests", asAdmin({ seller: "yutao", excerpt: EXCERPT }))).status, 404);
  } finally { await s.close(); }
});
