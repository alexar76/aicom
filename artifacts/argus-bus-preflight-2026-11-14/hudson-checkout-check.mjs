import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { chromium } from "playwright-core";

const merchant = "https://www.ridehudsonlink.com";
const endpoint = readFileSync(process.env.ARGUS_HUDSON_BROWSER_WS_FILE ?? "/run/checkout/hudson-browser-ws", "utf8").trim();
if (!/^ws:\/\/argus-hudson-browser:47871\/[a-f0-9]{64}$/.test(endpoint)) {
  throw new Error("Private Hudson Link browser endpoint is invalid");
}
const browser = await chromium.connect(endpoint, { timeout: 5_000 }).catch(() => {
  throw new Error("Private Hudson Link browser is unavailable");
});
try {
  const context = await browser.newContext({ locale: "en-US", serviceWorkers: "block" });
  try {
    await context.routeWebSocket("**/*", socket => socket.close());
    await context.route("**/*", async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== merchant || request.method() !== "GET") return route.abort().catch(() => {});
      try {
        const response = await route.fetch({ maxRedirects: 0, maxRetries: 0, timeout: 7_000 });
        try {
          if (response.status() !== 200) return await route.abort();
          await route.fulfill({ response });
        } finally { await response.dispose().catch(() => {}); }
      } catch { await route.abort().catch(() => {}); }
    });
    const page = await context.newPage();
    const response = await page.goto(`${merchant}/checkout`, { waitUntil: "domcontentloaded", timeout: 12_000 });
    assert.equal(response?.status(), 200);
    await page.getByRole("button", { name: "Continue With Card", exact: false }).waitFor({ timeout: 5_000 });
    const pdf = await page.pdf();
    assert.equal(pdf.subarray(0, 5).toString(), "%PDF-");
    console.log(JSON.stringify({ checkout_http: 200, native_card_button: true, chromium_can_print_pdf: true, payment_submitted: false }));
  } finally {
    await context.unrouteAll({ behavior: "ignoreErrors" });
    await context.close();
  }
} finally { await browser.close(); }
