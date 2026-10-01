import pkg from 'playwright';
const { chromium } = pkg;
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
await page.goto('https://monitor.modelmarket.dev/?node=oracle-chronos&lang=en', { waitUntil: 'commit', timeout: 90000 });
const t0 = Date.now();
let seen = null;
for (let i = 0; i < 30; i++) {
  await page.waitForTimeout(2000);
  const r = await page.evaluate(() => {
    const f = [...document.querySelectorAll('iframe')].find((x) => /embed=1/.test(x.src));
    if (!f) return null;
    return { opacity: getComputedStyle(f).opacity, size: `${Math.round(f.getBoundingClientRect().width)}x${Math.round(f.getBoundingClientRect().height)}` };
  });
  if (r) { seen = { ...r, atMs: Date.now() - t0 }; if (r.opacity === '1') break; }
}
console.log(JSON.stringify(seen));
await browser.close();
