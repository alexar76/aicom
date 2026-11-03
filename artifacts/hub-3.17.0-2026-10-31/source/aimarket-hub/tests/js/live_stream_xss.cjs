// Render live-stream.html against a hostile ?hub= feed; report whether markup executed.
const fs = require('fs');
const { JSDOM } = require(process.env.JSDOM_PATH);
const html = fs.readFileSync(process.argv[2], 'utf8');
const evil = '<img src=x onerror="window.__pwned=1">';
const feed = { summary: { peers_count: 2 }, events: [
  { capability_id: 'x', success: true, latency_ms: evil, price_usd: 1, source_hub: 'local' },
  { capability_id: 'y', success: true, latency_ms: 5, price_usd: 1, source_hub: evil },
] };
const dom = new JSDOM(html, {
  url: 'https://modelmarket.dev/widget/live-stream.html?hub=https://evil.example',
  runScripts: 'dangerously', pretendToBeVisual: true,
  beforeParse(w) {
    w.fetch = async () => ({ ok: true, status: 200, json: async () => feed });
    w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: () => () => {} });
    w.requestAnimationFrame = () => 0;
  },
});
setTimeout(() => {
  const w = dom.window;
  const imgs = w.document.querySelectorAll('img[onerror]').length;
  console.log(JSON.stringify({ injected_img_tags: imgs, pwned: !!w.__pwned }));
  process.exit(0);
}, 1500);
