/**
 * What does an oracle node's preview actually render in a real browser?
 *
 * swiftshader because the box this runs on has no GPU; the point is not fidelity but whether
 * the scene draws ANYTHING. The measurement is pixel variance inside the preview box: stars on
 * black have almost none, a real scene has plenty.
 */
import { chromium } from 'playwright';

const BASE = process.env.MONITOR_URL || 'https://monitor.modelmarket.dev/';
const NODES = (process.env.NODES || 'oracle-chronos,oracle-platon,oracle-lumen,basanos,themis').split(',');

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

// Abort the Google Fonts requests. Not to simulate an outage: `page.screenshot` waits for
// `document.fonts.ready`, and from this box fonts.googleapis.com does not answer, so the wait
// never ends and the probe times out before it measures anything. Aborting makes the promise
// resolve with fallback faces, which is irrelevant to whether a WebGL scene draws.
await page.route('**fonts.googleapis.com/**', (r) => r.abort());
await page.route('**fonts.gstatic.com/**', (r) => r.abort());

const errors = [];
const failed = [];
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`${m.type()}: ${m.text().slice(0, 200)}`); });
page.on('requestfailed', (r) => failed.push(`${r.failure()?.errorText} ${r.url().slice(0, 120)}`));
page.on('response', (r) => { if (r.status() >= 400) failed.push(`HTTP ${r.status()} ${r.url().slice(0, 120)}`); });

for (const node of NODES) {
  errors.length = 0; failed.length = 0;
  await page.goto(`${BASE}?node=${node}&lang=en`, { waitUntil: 'load', timeout: 60_000 });
  // Give the lazy chunk, the WebGL context and a few animation frames time to arrive.
  await page.waitForTimeout(9000);

  const report = await page.evaluate(() => {
    const canvases = [...document.querySelectorAll('canvas')];
    const panel = document.querySelector('[class*="fixed"], aside, [role="dialog"]');
    const out = { canvases: canvases.length, boxes: [] };
    for (const c of canvases) {
      const r = c.getBoundingClientRect();
      out.boxes.push({ w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top), left: Math.round(r.left) });
    }
    out.panelText = (panel?.textContent || '').replace(/\s+/g, ' ').slice(0, 160);
    out.iframes = [...document.querySelectorAll('iframe')].map((f) => f.src.slice(0, 100));
    return out;
  });

  // The preview canvas is the small one (the big one is the galaxy).
  const small = report.boxes
    .map((b, i) => ({ ...b, i }))
    .filter((b) => b.w > 100 && b.w < 700 && b.h > 100 && b.h < 700)
    .sort((a, b) => a.w - b.w)[0];

  // Read the GL canvas itself rather than the compositor: `toDataURL` inside a rAF catches the
  // frame that was just drawn, and a scene that renders nothing gives a near-uniform image
  // whatever the page around it looks like.
  let pixels = null;
  if (small) {
    pixels = await page.evaluate(async (idx) => {
      const c = [...document.querySelectorAll('canvas')][idx];
      if (!c) return null;
      const url = await new Promise((res) => requestAnimationFrame(() => {
        try { res(c.toDataURL('image/png')); } catch (e) { res(''); }
      }));
      if (!url) return { error: 'toDataURL blocked' };
      const img = new Image();
      await new Promise((res) => { img.onload = res; img.onerror = res; img.src = url; });
      const off = document.createElement('canvas');
      off.width = Math.min(img.width, 160); off.height = Math.min(img.height, 160);
      const ctx = off.getContext('2d');
      if (!ctx) return { error: 'no 2d ctx' };
      ctx.drawImage(img, 0, 0, off.width, off.height);
      const data = ctx.getImageData(0, 0, off.width, off.height).data;
      let lit = 0, sum = 0, max = 0;
      const distinct = new Set();
      for (let i = 0; i < data.length; i += 4) {
        const v = (data[i] + data[i + 1] + data[i + 2]) / 3;
        sum += v; if (v > 24) lit++; if (v > max) max = v;
        distinct.add(`${data[i] >> 4},${data[i + 1] >> 4},${data[i + 2] >> 4}`);
      }
      const n = data.length / 4;
      return { litPct: +(100 * lit / n).toFixed(1), meanLuma: +(sum / n).toFixed(1),
               maxLuma: max, distinctColors: distinct.size, w: img.width, h: img.height };
    }, small.i);

    try {
      const shot = await page.screenshot({
        clip: { x: small.left + 4, y: small.top + 4, width: small.w - 8, height: small.h - 8 },
        timeout: 8000,
      });
      const fs = await import('node:fs');
      fs.writeFileSync(`/tmp/preview-${node}.png`, shot);
    } catch { /* the pixel read above is the measurement that matters */ }
  }

  console.log(`\n=== ${node}`);
  console.log(`  canvases=${report.canvases} preview=${small ? `${small.w}x${small.h}` : 'NOT FOUND'}`);
  console.log(`  pixels: ${pixels ? JSON.stringify(pixels) : 'not sampled'}`);
  console.log(`  panel: ${report.panelText.slice(0, 110)}`);
  if (report.iframes.length) console.log(`  iframes: ${report.iframes.join(' | ')}`);
  if (failed.length) console.log(`  FAILED REQUESTS:\n    ${[...new Set(failed)].slice(0, 6).join('\n    ')}`);
  if (errors.length) console.log(`  CONSOLE:\n    ${[...new Set(errors)].slice(0, 6).join('\n    ')}`);
}

await browser.close();
