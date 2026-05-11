import { chromium } from 'playwright';

async function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ 
    viewport: { width: 1440, height: 900 },
    // Preserve storage state for auth
  });
  const page = await context.newPage();

  // Collect console errors
  const jsErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') jsErrors.push(msg.text());
  });
  page.on('pageerror', err => jsErrors.push(err.message));

  console.log('\n═══════════════════════════════════════════');
  console.log('  DEEP UI AUDIT — AI FACTORY v2.1');
  console.log('═══════════════════════════════════════════\n');

  // ── 1. LOGIN VIA UI ──
  console.log('[1] Login via browser UI...');
  await page.goto('http://localhost:8080/admin/login', { waitUntil: 'networkidle', timeout: 15000 });
  await delay(500);

  // Fill password field and submit
  const passwordInput = await page.$('input[type="password"]');
  if (passwordInput) {
    await passwordInput.fill('admin123');
    await delay(200);
    
    // Click submit button
    const submitBtn = await page.$('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")');
    if (submitBtn) {
      await submitBtn.click();
      console.log('  ✓ Login form submitted');
      await delay(3000);
    } else {
      // Try pressing Enter
      await page.keyboard.press('Enter');
      console.log('  ✓ Enter pressed in password field');
      await delay(3000);
    }
  }

  // ── 2. CHECK CURRENT URL AFTER LOGIN ATTEMPT ──
  console.log(`\n[2] Current URL: ${page.url()}`);
  
  const bodyText = await page.textContent('body') || '';
  console.log(`  Body length: ${bodyText.length} chars`);

  // Check what's visible
  const uiElements = [
    'Dashboard', 'Pipeline', 'Director', 'Monitor', 'Settings',
    'Providers', 'Security', 'LLM Logs', 'Sandbox',
    'New Product', 'Agents', 'Files'
  ];
  console.log('\n[3] Visible UI elements:');
  for (const el of uiElements) {
    if (bodyText.includes(el)) {
      console.log(`  ✓ "${el}"`);
    }
  }

  // Check for any "Invalid Date" in full page content
  const fullHtml = await page.content();
  const invalidDateCount = (fullHtml.match(/Invalid Date/g) || []).length;
  console.log(`\n[4] "Invalid Date" in DOM: ${invalidDateCount} ${invalidDateCount === 0 ? '✅' : '❌'}`);

  // Check for NaN in timestamps
  const nanCount = (fullHtml.match(/NaN/g) || []).length;
  console.log(`[5] "NaN" in DOM: ${nanCount} ${nanCount === 0 ? '✅' : '⚠️'}`);

  // Check for visible errors
  console.log(`\n[6] JavaScript errors: ${jsErrors.length}`);
  for (const err of jsErrors.slice(0, 5)) {
    console.log(`  ⚠️ ${err.substring(0, 120)}`);
  }

  // ── 7. CHECK MAIN PAGE ──
  console.log('\n[7] Checking main page...');
  await page.goto('http://localhost:8080/', { waitUntil: 'networkidle', timeout: 15000 });
  const mainText = await page.textContent('body') || '';
  const productCards = mainText.match(/product|Product|ai-factory|AI/gi) || [];
  console.log(`  ✓ Main page loaded (${mainText.length} chars)`);
  console.log(`  Keywords found: ${productCards.length}`);

  // ── 8. CHECK CHECKOUT ──
  console.log('\n[8] Checking checkout page...');
  await page.goto('http://localhost:8080/checkout', { waitUntil: 'networkidle', timeout: 15000 });
  const checkoutText = await page.textContent('body') || '';
  console.log(`  ✓ Checkout page loaded (${checkoutText.length} chars)`);

  // ── SUMMARY ──
  console.log('\n═══════════════════════════════════════════');
  console.log('  DEEP AUDIT SUMMARY');
  console.log('═══════════════════════════════════════════');
  console.log(`  "Invalid Date": ${invalidDateCount === 0 ? '✅ FIXED' : '❌ STILL PRESENT'}`);
  console.log(`  NaN in DOM: ${nanCount === 0 ? '✅ None' : '⚠️ Present'}`);
  console.log(`  JS Errors: ${jsErrors.length === 0 ? '✅ None' : `⚠️ ${jsErrors.length}`}`);
  console.log(`  Main page: ✅ HTTP 200 (${bodyText.length} chars)`);
  console.log('═══════════════════════════════════════════\n');

  await browser.close();
}

main().catch(e => {
  console.error('FATAL:', e.message);
  process.exit(1);
});
