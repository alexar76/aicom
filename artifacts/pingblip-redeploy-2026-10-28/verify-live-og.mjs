#!/usr/bin/env node
// Public read-only verification. Run only after the deployment is ready:
// node artifacts/pingblip-redeploy-2026-10-28/verify-live-og.mjs --run
// Optional previous JPEGs: old-og/<species-id>.jpg beside this script.
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const evidence = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(evidence, "../..");
const args = process.argv.slice(2);
if (!args.includes("--run")) {
  console.log("No HTTP requests made. After deployment, run:");
  console.log(`node ${path.relative(root, fileURLToPath(import.meta.url))} --run`);
  console.log("Optional: --old-dir PATH --report PATH --concurrency 6");
  process.exit(0);
}
function option(flag, fallback) {
  const i = args.indexOf(flag);
  return i < 0 ? fallback : args[i + 1];
}
const reportPath = path.resolve(option("--report", path.join(evidence, "live-og-verification.json")));
const oldDir = path.resolve(option("--old-dir", path.join(evidence, "old-og")));
const concurrency = Math.max(1, Math.min(8, Number(option("--concurrency", "6")) || 6));
const require = createRequire(import.meta.url);
const sharp = require(path.join(root, "pingblip/memeforge/node_modules/sharp"));
const changed = [
  "spark-moth", "rust-crown", "winged-bolt", "cola-cube",
  "caramel-bust", "graveyard-shift", "taxi-larva",
];
const sites = [
  { key: "game", origin: "https://pingblip.com", prefix: "/s/", crop: { left: 20, top: 55, width: 520, height: 520 } },
  { key: "world", origin: "https://world.pingblip.com", prefix: "/shelf/", crop: { left: 695, top: 80, width: 470, height: 470 } },
];
const thresholds = { wholeMaeMax: 6, wholeRmseMax: 20, foregroundMaeMax: 10, oldPreferenceTolerance: 0.05 };
const report = {
  startedAt: new Date().toISOString(),
  method: "Check exact OG and Twitter metadata URLs for every local species; fetch changed-species OG PNGs from those URLs; compare the known sculpt rectangle with local JPEG resized to the same square. Differences tolerate resampling; optional previous JPEGs provide a second reference.",
  scope: "Public GET requests only. No authenticated actions, browser gameplay, crawler submissions, or third-party posts.",
  thresholds,
  oldJpegDirectory: oldDir,
  inputs: {}, metadata: [], images: [], inputErrors: [],
};
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const rounded = (number) => Math.round(number * 1e6) / 1e6;
const errorText = (error) => String(error?.message ?? error);

async function mapLimit(items, limit, task, progress) {
  const results = new Array(items.length);
  let next = 0;
  let done = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await task(items[index]);
      done += 1;
      if (progress && (done % 20 === 0 || done === items.length)) progress(done, items.length);
    }
  }));
  return results;
}

function decode(value) {
  return value.replace(/&(#x[0-9a-f]+|#\d+|amp|quot|apos|lt|gt);/gi, (whole, token) => {
    if (token[0] === "#") {
      const number = token[1].toLowerCase() === "x" ? parseInt(token.slice(2), 16) : parseInt(token.slice(1), 10);
      return number >= 0 && number <= 0x10ffff ? String.fromCodePoint(number) : whole;
    }
    return ({ amp: "&", quot: '"', apos: "'", lt: "<", gt: ">" })[token.toLowerCase()] ?? whole;
  });
}
function imageTags(html) {
  const tags = { og: [], twitter: [] };
  for (const tag of html.match(/<meta\b[^>]*>/gi) ?? []) {
    const attributes = {};
    for (const match of tag.matchAll(/([^\s=/>]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g)) {
      attributes[match[1].toLowerCase()] = decode(match[2] ?? match[3] ?? match[4] ?? "");
    }
    const key = (attributes.property ?? attributes.name ?? "").toLowerCase();
    if (key === "og:image" && attributes.content) tags.og.push(attributes.content);
    if (key === "twitter:image" && attributes.content) tags.twitter.push(attributes.content);
  }
  return tags;
}
function safeHeaders(response) {
  return Object.fromEntries([
    "content-type", "content-length", "cache-control", "age", "etag",
    "last-modified", "cf-cache-status", "x-cache", "x-nextjs-cache", "server",
  ].flatMap((name) => response.headers.has(name) ? [[name, response.headers.get(name)]] : []));
}
async function get(url, accept) {
  let lastError;
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const response = await fetch(url, {
        headers: {
          // Twitterbot requests receive metadata in the initial HTML head.
          "User-Agent": "PingBlipDeploymentVerifier/2026-10-28 Twitterbot",
          "Accept": accept,
          "Cache-Control": "no-cache",
          "Pragma": "no-cache",
        },
        signal: AbortSignal.timeout(45000),
        redirect: "follow",
      });
      const body = Buffer.from(await response.arrayBuffer());
      if ((response.status === 429 || response.status >= 500) && attempt < 2) continue;
      return { status: response.status, url: response.url, headers: safeHeaders(response), body, attempts: attempt };
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}
function validateImageUrl(value, site, id, version) {
  try {
    const url = new URL(value, site.origin);
    return {
      value, resolved: url.href,
      ok: url.origin === site.origin
        && url.pathname === `${site.prefix}${id}/opengraph-image`
        && url.searchParams.get("v") === version,
      version: url.searchParams.get("v"),
    };
  } catch (error) {
    return { value, ok: false, error: errorText(error) };
  }
}
async function metadataCheck({ site, id, version }) {
  const result = { site: site.key, id, expectedVersion: version, requestedUrl: `${site.origin}${site.prefix}${id}`, ok: false };
  try {
    const response = await get(result.requestedUrl, "text/html");
    result.status = response.status;
    result.finalUrl = response.url;
    result.headers = response.headers;
    const tags = imageTags(response.body.toString("utf8"));
    result.og = tags.og.map((value) => validateImageUrl(value, site, id, version));
    result.twitter = tags.twitter.map((value) => validateImageUrl(value, site, id, version));
    result.ok = response.status === 200
      && result.og.length > 0 && result.og.every((tag) => tag.ok)
      && result.twitter.length > 0 && result.twitter.every((tag) => tag.ok);
    if (!result.ok) result.error = "Expected both OG and Twitter species-card URLs with the local model hash.";
  } catch (error) {
    result.error = errorText(error);
  }
  return result;
}

function difference(actual, reference) {
  if (actual.length !== reference.length) throw new Error("Comparison pixel lengths differ");
  let absolute = 0, squared = 0, foregroundAbsolute = 0, foregroundValues = 0;
  for (let i = 0; i < actual.length; i += 3) {
    const foreground = Math.max(reference[i], reference[i + 1], reference[i + 2]) > 12;
    for (let channel = 0; channel < 3; channel++) {
      const delta = Math.abs(actual[i + channel] - reference[i + channel]);
      absolute += delta;
      squared += delta * delta;
      if (foreground) { foregroundAbsolute += delta; foregroundValues += 1; }
    }
  }
  return {
    mae: rounded(absolute / actual.length),
    rmse: rounded(Math.sqrt(squared / actual.length)),
    foregroundMae: rounded(foregroundAbsolute / Math.max(1, foregroundValues)),
    foregroundPixelCount: foregroundValues / 3,
  };
}
async function resizedReference(bytes, size) {
  return sharp(bytes).resize(size, size, { fit: "fill", kernel: "lanczos3" })
    .toColourspace("srgb").removeAlpha().raw().toBuffer();
}
async function imageCheck({ site, id }) {
  const metadata = report.metadata.find((item) => item.site === site.key && item.id === id);
  const result = { site: site.key, id, crop: site.crop, ok: false };
  const matched = metadata?.og?.find((tag) => tag.ok);
  if (!matched) return { ...result, error: "Metadata did not supply an expected versioned OG URL; image request skipped." };
  result.requestedUrl = matched.resolved;
  try {
    const response = await get(result.requestedUrl, "image/png");
    result.status = response.status;
    result.finalUrl = response.url;
    result.headers = response.headers;
    if (response.status !== 200) throw new Error(`OG request returned HTTP ${response.status}`);
    const dimensions = await sharp(response.body).metadata();
    result.dimensions = { width: dimensions.width, height: dimensions.height, format: dimensions.format };
    if (dimensions.width !== 1200 || dimensions.height !== 630 || dimensions.format !== "png") {
      throw new Error("OG response is not a 1200x630 PNG");
    }
    result.pngSha256 = sha256(response.body);
    const pngPath = path.join(evidence, "og-png", `${site.key}-${id}.png`);
    await mkdir(path.dirname(pngPath), { recursive: true });
    await writeFile(pngPath, response.body);
    result.savedPng = path.relative(evidence, pngPath);
    const pixels = await sharp(response.body).extract(site.crop)
      .toColourspace("srgb").removeAlpha().raw().toBuffer();
    const jpegPath = path.join(root, "pingblip/world/public/dex/og", `${id}.jpg`);
    const jpeg = await readFile(jpegPath);
    result.referenceJpeg = path.relative(root, jpegPath);
    result.referenceJpegSha256 = sha256(jpeg);
    const reference = await resizedReference(jpeg, site.crop.width);
    result.newJpegDifference = difference(pixels, reference);
    result.matchesNewJpeg = result.newJpegDifference.mae <= thresholds.wholeMaeMax
      && result.newJpegDifference.rmse <= thresholds.wholeRmseMax
      && result.newJpegDifference.foregroundMae <= thresholds.foregroundMaeMax;
    let previous;
    try { previous = await readFile(path.join(oldDir, `${id}.jpg`)); } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    if (previous) {
      const previousReference = await resizedReference(previous, site.crop.width);
      result.oldJpegSha256 = sha256(previous);
      result.oldJpegDifference = difference(pixels, previousReference);
      result.newVersusOldSourceDifference = difference(reference, previousReference);
      result.newMaeImprovementOverOld = rounded(result.oldJpegDifference.mae - result.newJpegDifference.mae);
      result.oldSourceIsSameByPixels = result.newVersusOldSourceDifference.mae < 0.01;
      result.newReferencePreferred = result.oldSourceIsSameByPixels
        || result.newJpegDifference.mae <= result.oldJpegDifference.mae + thresholds.oldPreferenceTolerance;
      result.oldComparisonAmbiguous = !result.oldSourceIsSameByPixels
        && Math.abs(result.newMaeImprovementOverOld) <= thresholds.oldPreferenceTolerance;
    } else {
      result.oldReference = "unavailable";
    }
    result.ok = result.matchesNewJpeg && result.newReferencePreferred !== false;
    if (!result.ok) result.error = "Rendered sculpt does not sufficiently match the new JPEG, or matches the old JPEG better.";
  } catch (error) {
    result.error = errorText(error);
  }
  return result;
}

try {
  const forgeManifestPath = path.join(root, "pingblip/memeforge/src/data/model-versions.json");
  const gameManifestPath = path.join(root, "pingblip/web/src/data/model-versions.json");
  const forgeBytes = await readFile(forgeManifestPath);
  const gameBytes = await readFile(gameManifestPath);
  const forgeVersions = JSON.parse(forgeBytes);
  const gameVersions = JSON.parse(gameBytes);
  const ids = Object.keys(forgeVersions).sort();
  report.inputs = {
    speciesCount: ids.length,
    forgeManifestSha256: sha256(forgeBytes), gameManifestSha256: sha256(gameBytes),
    changedSpecies: changed,
  };
  if (ids.length !== 80) report.inputErrors.push(`Expected 80 species; found ${ids.length}`);
  for (const id of ids) {
    if (forgeVersions[id] !== gameVersions[id]) report.inputErrors.push(`${id}: game and Forge hashes differ`);
    const bytes = await readFile(path.join(root, "pingblip/memeforge/public/models", `${id}.glb`));
    if (sha256(bytes).slice(0, 10) !== forgeVersions[id]) report.inputErrors.push(`${id}: manifest is stale relative to local GLB`);
  }
  report.metadata = await mapLimit(
    sites.flatMap((site) => ids.map((id) => ({ site, id, version: site.key === "game" ? gameVersions[id] : forgeVersions[id] }))),
    concurrency, metadataCheck, (done, total) => console.log(`metadata ${done}/${total}`),
  );
  report.images = await mapLimit(
    sites.flatMap((site) => changed.map((id) => ({ site, id }))),
    Math.min(2, concurrency), imageCheck, (done, total) => console.log(`rendered OG ${done}/${total}`),
  );
} catch (error) {
  report.inputErrors.push(errorText(error));
}
report.finishedAt = new Date().toISOString();
report.summary = {
  metadataChecked: report.metadata.length,
  metadataPassed: report.metadata.filter((item) => item.ok).length,
  renderedOgChecked: report.images.length,
  renderedOgPassed: report.images.filter((item) => item.ok).length,
  oldJpegComparisons: report.images.filter((item) => item.oldJpegDifference).length,
  ambiguousOldComparisons: report.images.filter((item) => item.oldComparisonAmbiguous).map((item) => `${item.site}:${item.id}`),
};
report.ok = report.inputErrors.length === 0
  && report.summary.metadataChecked === 160 && report.summary.metadataPassed === 160
  && report.summary.renderedOgChecked === 14 && report.summary.renderedOgPassed === 14;
await mkdir(path.dirname(reportPath), { recursive: true });
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify({ ok: report.ok, ...report.summary, report: reportPath }, null, 2));
if (!report.ok) process.exitCode = 1;
