/**
 * Browser-side acceptance check for the Alien Monitor page.
 *
 * Answers, with numbers rather than impressions:
 *   1. does the oracle node card show a preview, and is it the portal iframe or a canvas
 *   2. how many oracle nodes the scene actually knows about
 *   3. what the galaxy canvas is really costing (context attributes + backing-store size)
 *   4. frames per second
 *
 * Runs Chromium (which is what Chrome is) under swiftshader, so FPS is a RELATIVE figure:
 * useful for before/after on the same box, meaningless as an absolute.
 *
 *   node scripts/verify_monitor_ui.mjs                       # live page
 *   PAGE=http://127.0.0.1:9100/ node scripts/verify_monitor_ui.mjs
 */
import pkg from 'playwright';
const { chromium } = pkg;

const PAGE = process.env.PAGE || 'https://monitor.modelmarket.dev/';
const NODES = (process.env.NODES || 'oracle-chronos,oracle-platon,oracle-lumen').split(',');

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
// Fonts are deliberately NOT aborted: blocking them can hold back an iframe's `load` event,
// and the preview's visibility is gated on exactly that event. Do not "optimise" this away.

let first = true;
for (const node of NODES) {
  try {
    await page.goto(`${PAGE}?node=${node}&lang=en`, { waitUntil: 'commit', timeout: 120_000 });
  } catch (e) {
    console.log(`\n${node}: navigation failed — ${String(e).split('\n')[0]}`);
    continue;   // one slow node must not abort the whole run
  }
  try {
    await page.waitForFunction(() => document.querySelectorAll('canvas').length > 0, { timeout: 60_000 });
  } catch { /* reported below */ }
  // The portal embed fires `load` around 4.8s (measured), and the card only mounts once the
  // websocket has delivered nodes — so this wait has to cover both, not just the first.
  await page.waitForTimeout(22_000);

  const out = await page.evaluate(async () => {
    const canvases = [...document.querySelectorAll('canvas')];
    const big = canvases.map((c) => ({ c, r: c.getBoundingClientRect() }))
      .sort((a, b) => b.r.width * b.r.height - a.r.width * a.r.height)[0];
    let gl = null;
    if (big) {
      const ctx = big.c.getContext('webgl2') || big.c.getContext('webgl');
      const attrs = ctx?.getContextAttributes?.();
      gl = {
        cssSize: `${Math.round(big.r.width)}x${Math.round(big.r.height)}`,
        backingStore: `${big.c.width}x${big.c.height}`,
        effectiveDpr: +(big.c.width / Math.max(1, big.r.width)).toFixed(2),
        antialias: attrs?.antialias ?? null,
        preserveDrawingBuffer: attrs?.preserveDrawingBuffer ?? null,
      };
    }
    const frames = await new Promise((res) => {
      let n = 0; const t0 = performance.now();
      const tick = () => { n++; if (performance.now() - t0 < 5000) requestAnimationFrame(tick); else res(n / ((performance.now() - t0) / 1000)); };
      requestAnimationFrame(tick);
    });
    const iframes = [...document.querySelectorAll('iframe')].map((f) => ({
      src: f.src.slice(0, 80), visible: getComputedStyle(f).opacity !== '0',
      size: `${Math.round(f.getBoundingClientRect().width)}x${Math.round(f.getBoundingClientRect().height)}`,
    }));
    // The scene's own node list, straight from the DOM labels it draws.
    const text = document.body.textContent || '';
    const oracles = ['platon', 'chronos', 'lattice', 'murmuration', 'lumen', 'colony', 'turing',
      'percola', 'fermat', 'ablation', 'landauer', 'sortes', 'gauss', 'aestus', 'betti',
      'kantor', 'fourier'];
    const present = oracles.filter((o) => new RegExp(o, 'i').test(text));
    return { canvases: canvases.length, gl, fps: +frames.toFixed(1), iframes,
             oraclesNamedOnPage: present.length, missing: oracles.filter((o) => !present.includes(o)) };
  });

  if (first) {
    console.log(`galaxy canvas: ${out.gl ? JSON.stringify(out.gl) : 'not found'}`);
    console.log(`fps (swiftshader, relative): ${out.fps}`);
    console.log(`oracles named on the page: ${out.oraclesNamedOnPage}/17`
      + (out.missing.length ? ` — missing: ${out.missing.join(', ')}` : ''));
    first = false;
  }
  const preview = out.iframes.find((f) => /\?o=|embed=1/.test(f.src));
  console.log(`\n${node}: canvases=${out.canvases} preview=${preview ? `iframe ${preview.size} visible=${preview.visible}` : 'NO PORTAL IFRAME'}`);
  if (preview) console.log(`  src: ${preview.src}`);
}

await browser.close();
