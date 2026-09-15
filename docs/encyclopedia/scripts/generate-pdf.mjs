#!/usr/bin/env node
/**
 * Generate PDF encyclopedia from HTML via Playwright
 * Usage: node docs/encyclopedia/scripts/generate-pdf.mjs [en|ru|es|all]
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PDF_DIR = path.join(ROOT, 'pdf');
const LOCALES = ['en', 'ru', 'es'];

async function generatePdf(browser, locale) {
  const htmlPath = path.join(ROOT, locale, 'index.html');
  if (!fs.existsSync(htmlPath)) {
    throw new Error(`Missing ${htmlPath} — run generate-encyclopedia.mjs first`);
  }
  const fileUrl = `file://${htmlPath}`;
  const page = await browser.newPage();
  await page.emulateMedia({ media: 'print' });
  await page.goto(fileUrl, { waitUntil: 'load', timeout: 120000 });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() =>
    Promise.all(
      Array.from(document.images).map(
        (img) =>
          img.complete && img.naturalWidth > 0
            ? Promise.resolve()
            : new Promise((resolve) => {
                img.addEventListener('load', resolve, { once: true });
                img.addEventListener('error', resolve, { once: true });
              })
      )
    )
  );
  const broken = await page.evaluate(() =>
    Array.from(document.images)
      .filter((img) => !img.naturalWidth)
      .map((img) => img.alt || img.src.slice(0, 80))
  );
  if (broken.length) {
    console.error(`  ! ${broken.length} images failed:`, broken.slice(0, 5));
    throw new Error(`PDF aborted: ${broken.length} broken image(s) in ${locale}`);
  }
  await page.waitForTimeout(500);

  const outPath = path.join(PDF_DIR, `aicom-encyclopedia-${locale}.pdf`);
  await page.pdf({
    path: outPath,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    margin: { top: '0', bottom: '12mm', left: '0', right: '0' },
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: `<div style="width:100%;margin:0;padding:4mm 12mm 0;font-size:8px;line-height:1.4;color:#8b7cc8;text-align:center;font-family:Georgia,serif;background:#0a0520;-webkit-print-color-adjust:exact;print-color-adjust:exact;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
  });
  await page.close();
  const size = (fs.statSync(outPath).size / 1024 / 1024).toFixed(2);
  console.log(`  ✓ pdf/aicom-encyclopedia-${locale}.pdf (${size} MB)`);
}

async function main() {
  const arg = process.argv[2] || 'all';
  const targets = arg === 'all' ? LOCALES : [arg];
  fs.mkdirSync(PDF_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  for (const locale of targets) {
    console.log(`PDF: ${locale}`);
    await generatePdf(browser, locale);
  }
  await browser.close();
  console.log('Done.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
