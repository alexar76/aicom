import { chromium } from 'playwright';

const ADMIN_URL = 'http://localhost:8080/admin/login';
const FRONTEND_URL = 'http://localhost:8080';

async function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  console.log('\n═══════════════════════════════════════════');
  console.log('  UI AUDIT — AI FACTORY v2.1');
  console.log('═══════════════════════════════════════════\n');

  // ── 1. ADMIN LOGIN ──
  console.log('[1/6] Checking admin login page...');
  await page.goto(ADMIN_URL, { waitUntil: 'networkidle', timeout: 15000 });
  console.log(`  ✓ Page loaded: ${await page.title()}`);
  
  // Check for login form
  const loginForm = await page.$('input[type="password"], input[name="password"]');
  console.log(`  ${loginForm ? '✓' : '✗'} Password field found: ${!!loginForm}`);

  // Try to login via API directly (the frontend might use a different login flow)
  // Let's navigate to admin page after getting token via page API
  console.log('\n[2/6] Logging in via API...');
  const token = await page.evaluate(async () => {
    try {
      const resp = await fetch('/api/admin/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'admin123' })
      });
      const data = await resp.json();
      return data.access_token || data.token || null;
    } catch (e) { return null; }
  });
  console.log(`  ${token ? '✓' : '✗'} Token obtained: ${token ? token.substring(0,20)+'...' : 'NO'}`);

  // ── 2. ADMIN DASHBOARD ──
  console.log('\n[3/6] Checking Admin Dashboard page...');
  await page.goto('http://localhost:8080/admin', { waitUntil: 'networkidle', timeout: 15000 });
  await delay(2000);
  
  // Check for errors in console
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  
  const pageContent = await page.content();
  const hasErrors = pageContent.includes('error') || pageContent.includes('Error');
  const hasReactRoot = pageContent.includes('__NEXT_DATA__') || pageContent.includes('next');
  console.log(`  ✓ Page rendered (${pageContent.length} bytes), React: ${hasReactRoot}`);
  
  // Look for visible text
  const bodyText = await page.textContent('body') || '';
  const keyPhrases = ['Dashboard', 'Pipeline', 'Director', 'Monitor', 'Settings'];
  for (const phrase of keyPhrases) {
    console.log(`  ${bodyText.includes(phrase) ? '✓' : '○'} "${phrase}" ${bodyText.includes(phrase) ? 'found' : 'not visible (maybe behind login)'}`);
  }

  // ── 3. CHECK FOR 'Invalid Date' IN RENDERED HTML ──
  console.log('\n[4/6] Checking for "Invalid Date" bug...');
  const invalidDateCount = (pageContent.match(/Invalid Date/g) || []).length;
  console.log(`  ${invalidDateCount === 0 ? '✓' : '✗'} "Invalid Date" occurrences: ${invalidDateCount}`);

  // ── 4. CHECK ALL ROUTES ──
  console.log('\n[5/6] Checking frontend routes...');
  const routes = [
    '/', '/admin', '/admin/login', '/docs', '/checkout',
  ];
  for (const route of routes) {
    try {
      const resp = await page.goto(`http://localhost:8080${route}`, { 
        waitUntil: 'domcontentloaded', timeout: 10000 
      });
      const status = resp?.status() || 0;
      console.log(`  ${status === 200 ? '✓' : '✗'} ${route} -> HTTP ${status}`);
    } catch (e) {
      console.log(`  ✗ ${route} -> ERROR: ${e.message}`);
    }
  }

  // ── 5. CHECK API ENDPOINTS ──
  console.log('\n[6/6] Checking critical API endpoints...');
  const apiEndpoints = [
    { name: 'Health', url: '/api/health' },
    { name: 'Categories', url: '/api/products/categories' },
  ];
  for (const ep of apiEndpoints) {
    try {
      const resp = await page.goto(`http://localhost:8081${ep.url}`, { 
        waitUntil: 'domcontentloaded', timeout: 10000 
      });
      const status = resp?.status() || 0;
      const text = await page.textContent('body') || '';
      const isJson = text.startsWith('{') || text.startsWith('[');
      console.log(`  ${status === 200 ? '✓' : '✗'} ${ep.name} (${ep.url}) -> HTTP ${status}, JSON: ${isJson}`);
    } catch (e) {
      console.log(`  ✗ ${ep.name} -> ERROR: ${e.message}`);
    }
  }

  // ── FINAL SUMMARY ──
  console.log('\n═══════════════════════════════════════════');
  console.log('  UI AUDIT COMPLETE');
  console.log('═══════════════════════════════════════════\n');

  await browser.close();
}

main().catch(e => {
  console.error('FATAL:', e.message);
  process.exit(1);
});
