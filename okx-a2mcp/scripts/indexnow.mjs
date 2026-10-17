#!/usr/bin/env node
// Tell IndexNow (Bing, Yandex, Seznam, Naver, Yep — and through Bing, DuckDuckGo, Yahoo and Ecosia)
// which /tools/ pages exist, after a deploy. The key is public by design and proved by the file the
// gateway serves at https://modelmarket.dev/tools/<key>.txt — a key under /tools/ vouches for the
// /tools/ pages only, which is all this submits. Google does not take IndexNow; it reads the sitemap.
//
//   node scripts/indexnow.mjs            # submit
//   node scripts/indexnow.mjs --dry-run  # print what would be sent
import { readFileSync } from "node:fs";

const KEY = readFileSync(new URL("../src/web/indexnow-key.txt", import.meta.url), "utf8").trim();
const ORIGIN = "https://modelmarket.dev";
const KEY_URL = `${ORIGIN}/tools/${KEY}.txt`;
const UA = { "User-Agent": "modelmarket-tools-indexnow/1.0" };
const dryRun = process.argv.includes("--dry-run");

const served = await fetch(KEY_URL, { headers: UA });
if (!served.ok || (await served.text()).trim() !== KEY) {
  console.log(`key file not served at ${KEY_URL} — nothing sent`);
  process.exit(1);
}
const xml = await (await fetch(`${ORIGIN}/tools/sitemap.xml`, { headers: UA })).text();
const urlList = [...new Set([...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1].trim()))]
  .filter((u) => u.startsWith(`${ORIGIN}/tools/`));
if (!urlList.length) {
  console.log("sitemap: no /tools/ URLs — nothing sent");
  process.exit(1);
}
if (dryRun) {
  console.log(`would send ${urlList.length} URLs`, urlList.slice(0, 3), "…");
  process.exit(0);
}
const res = await fetch("https://api.indexnow.org/indexnow", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8", ...UA },
  body: JSON.stringify({ host: new URL(ORIGIN).hostname, key: KEY, keyLocation: KEY_URL, urlList }),
});
// 200 and 202 are both "received"; 403 = key not matched, 422 = URLs not under the key's path.
console.log(`indexnow: ${urlList.length} URLs → HTTP ${res.status}`);
process.exit(res.status === 200 || res.status === 202 ? 0 : 1);
