// vet402 (https://vet402.com) buys from x402 sellers and publishes what each paid call returned. Its
// badge for this site is shown on /tools/. The page's CSP allows images from this origin only, and a
// visitor's browser should not call a third party just to render the page, so the gateway fetches
// the badge itself (at most once an hour), checks it is a plain SVG, and serves it from /tools/.
export const VET402_BADGE_URL = "https://vet402.com/api/badge/host/modelmarket.dev.svg";
export const VET402_RECORD_URL = "https://vet402.com/sellers/modelmarket.dev";

const MAX_BYTES = 20_000;
// Anything that could run, load or link something. The badge is rectangles and text; a badge that
// carries more than that is not served.
const FORBIDDEN = /<script|<foreignobject|<image|<iframe|<object|<embed|<use\b|<a\b|<style|<!entity|<!doctype|<\?xml-stylesheet|\bon[a-z]+\s*=|javascript:|href\s*=|url\s*\(|@import/i;

/** The badge text if it is a plain SVG we are willing to serve from this origin, else null. */
export function safeBadge(text) {
  if (typeof text !== "string" || text.length === 0 || text.length > MAX_BYTES) return null;
  const s = text.trim();
  if (!/^<svg[\s>]/.test(s) || !s.endsWith("</svg>")) return null;
  if (FORBIDDEN.test(s)) return null;
  return s;
}

/**
 * A badge fetched on demand and kept for `ttlMs`. A failed refresh keeps serving the last good copy
 * (and retries after `retryMs`); with no good copy at all, get() answers null and the route is a 404.
 */
export function createBadgeCache({ url = VET402_BADGE_URL, ttlMs = 3_600_000, retryMs = 600_000, timeoutMs = 8_000,
                                   fetchFn = globalThis.fetch, now = () => Date.now() } = {}) {
  let good = null;      // { svg, fetchedAt }
  let nextTry = 0;
  let inflight = null;

  async function refresh() {
    try {
      const res = await fetchFn(url, {
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
        headers: { "User-Agent": "modelmarket.dev-tools/1 (+https://modelmarket.dev/tools/)", Accept: "image/svg+xml" },
      });
      const type = res.headers?.get?.("content-type") || "";
      const svg = res.ok && type.startsWith("image/svg+xml") ? safeBadge(await res.text()) : null;
      if (svg) {
        good = { svg, fetchedAt: now() };
        nextTry = now() + ttlMs;
        return;
      }
    } catch {
      // keep the last good copy
    }
    nextTry = now() + retryMs;
  }

  return {
    async get() {
      if (now() >= nextTry) {
        inflight ??= refresh().finally(() => { inflight = null; });
        if (!good) await inflight;   // first request waits; later ones get the cached copy at once
      }
      return good;
    },
  };
}
