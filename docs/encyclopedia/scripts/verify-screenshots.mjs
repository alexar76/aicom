#!/usr/bin/env node
/**
 * QA: ensure encyclopedia screenshots exist and are not empty loading placeholders.
 * Usage: node docs/encyclopedia/scripts/verify-screenshots.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execFileSync } from 'child_process';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const SHOTS = path.join(ROOT, 'assets/screenshots');
const PY_SCRIPT = path.join(__dirname, '_verify_screenshot_brightness.py');
const LOCALES = ['en', 'ru', 'es'];
const FILES = [
  'public-home.png',
  'admin-dashboard.png',
  'admin-pipeline.png',
  'admin-live-monitor.png',
  'admin-discovery.png',
];
const MIN_BYTES = 60_000;

function analyzePng(filePath) {
  try {
    const out = execFileSync('python3', [PY_SCRIPT, filePath], { encoding: 'utf8' }).trim();
    return { ok: true, detail: out };
  } catch (e) {
    const msg = (e.stderr || e.stdout || e.message || '').trim();
    return { ok: false, detail: msg || 'analysis failed' };
  }
}

let failed = 0;

for (const locale of LOCALES) {
  console.log(`\n${locale}:`);
  for (const file of FILES) {
    const p = path.join(SHOTS, locale, file);
    if (!fs.existsSync(p)) {
      console.log(`  ✗ ${file} — missing`);
      failed += 1;
      continue;
    }
    const size = fs.statSync(p).size;
    if (size < MIN_BYTES) {
      console.log(`  ✗ ${file} — too small (${size} bytes)`);
      failed += 1;
      continue;
    }
    const { ok, detail } = analyzePng(p);
    if (!ok) {
      console.log(`  ✗ ${file} — ${detail}`);
      failed += 1;
    } else {
      console.log(`  ✓ ${file} (${Math.round(size / 1024)} KB, ${detail})`);
    }
  }
}

for (const file of ['alien-ecosystem.png', 'alien-simulation.png']) {
  const p = path.join(SHOTS, 'shared', file);
  if (!fs.existsSync(p)) {
    console.log(`\nshared: ✗ ${file} — missing`);
    failed += 1;
  } else {
    console.log(`\nshared: ✓ ${file}`);
  }
}

if (failed) {
  console.error(`\n${failed} screenshot check(s) failed — re-run capture-localized-screenshots.mjs`);
  process.exit(1);
}
console.log('\nAll screenshots OK.');
