#!/usr/bin/env node
/** Quick visual QA — screenshot print preview pages for manual review */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'qa-screenshots');
const locale = process.argv[2] || 'ru';
const pages = (process.argv[3] || '1,5,6,7').split(',').map(Number);

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const html = path.join(ROOT, locale, 'index.html');
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage();
  await page.emulateMedia({ media: 'print' });
  await page.goto(`file://${html}`, { waitUntil: 'networkidle', timeout: 120000 });
  await page.evaluate(() => document.fonts.ready);

  const pdfPath = path.join(OUT, `preview-${locale}.pdf`);
  await page.pdf({
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    margin: { top: '16mm', bottom: '14mm', left: '0', right: '0' },
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: `<div style="width:100%;padding:5mm 12mm 0;font-size:8px;color:#8b7cc8;text-align:center;font-family:Georgia,serif;background:#0a0520;-webkit-print-color-adjust:exact;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
  });

  // Rasterize selected pages via canvas in browser (pdf.js lite — use full page height slices)
  const pageHeight = await page.evaluate(() => {
    const h = document.body.scrollHeight;
    return h;
  });
  const a4px = 1123; // ~297mm at 96dpi scaled
  for (const p of pages) {
    const y = Math.max(0, (p - 1) * a4px);
    await page.screenshot({
      path: path.join(OUT, `${locale}-page-${String(p).padStart(2, '0')}.png`),
      clip: { x: 0, y, width: 794, height: Math.min(a4px, pageHeight - y) },
      fullPage: false,
    });
    console.log(`  saved page ~${p}`);
  }
  await browser.close();
  console.log(`QA previews in ${OUT}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
