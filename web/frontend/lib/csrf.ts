/**
 * The double-submit CSRF header, in ONE place.
 *
 * `web/backend/middleware/csrf.py` enforces on the CREDENTIAL, not the path: any request
 * carrying an `access_token` / `aif_admin_session` cookie must present `X-CSRF-Token`.
 * `lib/api.ts` attaches it for unsafe methods, but three call sites used a raw `fetch` and
 * did not — so each worked for anonymous visitors and returned 403 for anyone with a
 * session. On the public-demo host that is every visitor who has clicked "Open demo":
 *
 *   - the landing page's own "build me a landing" CTA (/api/public/generate-landing)
 *   - the lead form (/api/marketing/lead), which surfaced "Failed to submit"
 *   - marketing analytics, which failed silently behind `.catch(() => {})`
 *
 * A raw fetch is sometimes the right tool (keepalive beacons, streaming), so the fix is a
 * shared helper rather than a rule that everything must go through the API client.
 */
export function csrfHeaders(): Record<string, string> {
  if (typeof document === 'undefined') return {};
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return m ? { 'X-CSRF-Token': decodeURIComponent(m[1]) } : {};
}
