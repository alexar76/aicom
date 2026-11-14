// Local fare-only check: node logan-check.mjs
// Existing sidecar, with the optional guest browser check:
// ssh attested 'docker exec -i -w /app argus-checkout-browser node --input-type=module - --sidecar' < logan-check.mjs
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const checkout = 'https://loganexpress.com/#/buy-bus-tickets-back-bay';
const apiPath = '/wp-content/plugins/lex_app/api.php';
const fareQuery = '?method=getProductById&productId=6';
const fareUrl = `https://loganexpress.com${apiPath}${fareQuery}`;
const version = '?ver=1.0.47';
const releasePath = '/smartstubsExternalWebsites/lex/lex-app-plugin/aws-0.1/';
const releaseOrigin = 'https://smartstubs-application-releases.s3.amazonaws.com';
const googleRoutes = new Set(['/recaptcha/api.js', '/recaptcha/api2/anchor', '/recaptcha/api2/bframe', '/recaptcha/api2/webworker.js']);
const challenge = 'iframe[src*="/recaptcha/api2/bframe"]:visible, iframe[src*="/recaptcha/api2/anchor"]:not([src*="size=invisible"]):visible';

function allowedGet(request) {
  if (request.method() !== 'GET' || request.postData() !== null) return false;
  const url = new URL(request.url());
  if (url.protocol !== 'https:' || url.username || url.password || url.port) return false;
  if (url.origin === new URL(checkout).origin) {
    if (url.pathname === '/') return request.resourceType() === 'document' && !url.search;
    if (url.pathname === apiPath) return [fareQuery, '?method=getAllPublicNotifications'].includes(url.search);
    return request.resourceType() === 'script' && /^\/wp-includes\/js\/jquery\/jquery(?:-migrate)?\.min\.js$/.test(url.pathname);
  }
  if (url.origin === releaseOrigin && url.pathname.startsWith(releasePath)) {
    return url.search === version && ['app.js', 'chunk-vendors.js', 'app.css'].includes(url.pathname.slice(releasePath.length));
  }
  if (url.origin === 'https://www.google.com') return googleRoutes.has(url.pathname);
  return url.origin === 'https://www.gstatic.com' && /^\/recaptcha\/(?:releases|api2)\//.test(url.pathname);
}

async function publicFare() {
  const response = await fetch(fareUrl, { method: 'GET', redirect: 'error', signal: AbortSignal.timeout(8_000) });
  assert.equal(response.status, 200);
  const product = await response.json();
  assert.equal(product.productId, 6);
  assert.equal(product.descriptionRegularTrip, 'BB - BOS');
  assert.equal(product.flexibleProduct, true);
  const airport = product.dropoffLocations.find(row => row.locationId === 1);
  assert.equal(airport?.description, 'Boston Logan International Airport');
  const fares = [6, 7].map(from => {
    const ranges = product.pricingDateRanges.filter(row => row.active && row.productId === 6
      && row.fromLocationId === from && row.toLocationId === 1 && row.startDate === null && row.endDate === null);
    assert.equal(ranges.length, 1);
    const tier = ranges[0].productTiers.find(row => row.tierId === 6 && row.description === 'Regular' && !row.isReturnTrip);
    assert.equal(tier?.price, 3);
    assert(product.productAvailabilities.some(row => row.active && !row.returnTrip));
    return { from: product.pickupLocations.find(row => row.locationId === from).description,
      to: airport.description, direction: 'one_way', kind: tier.description, fareCents: Math.round(tier.price * 100) };
  });
  return { source: fareUrl, productId: product.productId, currency: 'USD', fares };
}

async function sidecarOffer() {
  const { chromium } = await import('playwright-core');
  const endpoint = (await readFile('/run/checkout/browser-ws', 'utf8')).trim();
  assert(/^ws:\/\/argus-checkout-browser:47871\/[A-Za-z0-9_-]{32,128}$/.test(endpoint), 'Invalid private browser endpoint');
  const browser = await chromium.connect(endpoint, { timeout: 5_000 }).catch(() => { throw new Error('Private browser connection failed'); });
  try {
    const context = await browser.newContext({ serviceWorkers: 'block', locale: 'en-US', acceptDownloads: false });
    const allowedResponses = {};
    const blocked = { nonGet: 0, outsideAllowlist: 0 };
    await context.routeWebSocket('**/*', socket => socket.close());
    await context.route('**/*', async route => {
      const request = route.request();
      if (!allowedGet(request)) {
        if (request.method() === 'GET') blocked.outsideAllowlist++;
        else blocked.nonGet++;
        return route.abort();
      }
      try {
        const response = await route.fetch({ maxRedirects: 0, maxRetries: 0, timeout: 7_000 });
        try {
          const url = new URL(request.url());
          const suffix = url.pathname === apiPath ? `/${url.searchParams.get('method')}` : '';
          allowedResponses[`${url.origin}${url.pathname}${suffix}`] = response.status();
          if (response.status() !== 200) return await route.abort();
          await route.fulfill({ response });
        } finally {
          await response.dispose();
        }
      } catch {
        await route.abort().catch(() => {});
      }
    });

    const page = await context.newPage();
    const response = await page.goto(checkout, { waitUntil: 'domcontentloaded', timeout: 15_000 });
    assert.equal(response?.status(), 200);
    assert.equal(page.url(), checkout);
    const ready = page.getByRole('button', { name: 'Increase Regular ticket quantity', exact: true });
    const obstacle = page.locator(challenge).first();
    await ready.or(obstacle).first().waitFor({ state: 'visible', timeout: 12_000 }).catch(() => {});

    let state = 'checkout_control_unavailable';
    let quote;
    if (await obstacle.isVisible()) state = 'interactive_verification_required';
    else if (await ready.isVisible()) {
      await ready.click({ timeout: 3_000 });
      const regular = await page.getByRole('spinbutton', { name: 'Regular ticket quantity', exact: true }).inputValue({ timeout: 3_000 });
      const child = await page.getByRole('spinbutton', { name: 'Child ticket quantity', exact: true }).inputValue({ timeout: 3_000 });
      const subtotal = await page.getByText('Subtotal', { exact: true }).locator('..').innerText({ timeout: 3_000 });
      assert.equal(regular, '1');
      assert.equal(child, '0');
      assert.equal(subtotal.replace(/\s+/g, ' ').trim(), 'Subtotal $3.00');
      quote = { regularTickets: 1, childTickets: 0, subtotalCents: 300,
        cardFieldVisible: await page.locator('#purchInfo-cardNumber').isVisible() };
      state = await obstacle.isVisible() ? 'interactive_verification_required' : 'subtotal_verified';
    }
    return { checkout, state, quote, publicGetResponses: allowedResponses, blocked };
  } finally {
    await browser.close();
  }
}

const result = { checkedAt: new Date().toISOString(), fare: await publicFare() };
if (process.argv.includes('--sidecar')) result.browser = await sidecarOffer();
console.log(JSON.stringify(result, null, 2));
