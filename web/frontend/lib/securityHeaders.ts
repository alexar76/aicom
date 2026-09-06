/**
 * Security headers for the Next.js storefront and admin UI.
 * API responses use FastAPI middleware in web/backend/main.py (stricter default CSP).
 */

/** CSP when AIFACTORY_ENABLE_DEFAULT_CSP=1 and AIFACTORY_FRONTEND_CSP is unset. */
export const DEFAULT_FRONTEND_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com",
  // styles/globals.css opens with `@import url('https://fonts.googleapis.com/...')`, so a
  // style-src of 'self' alone blocks the site's own three webfonts and every page silently
  // falls back to system fonts. web/backend/api/agents_page.py already allows this origin —
  // this copy did not, which is the whole bug. fonts.gstatic.com serves the font FILES that
  // stylesheet then references, so font-src has to allow it too.
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "img-src 'self' data: blob: https:",
  "media-src 'self' blob:",
  "font-src 'self' data: https://fonts.gstatic.com",
  "connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com https://www.googletagmanager.com https://region1.google-analytics.com",
  "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join('; ');

export function resolveFrontendCsp(): string | null {
  const explicit = (process.env.AIFACTORY_FRONTEND_CSP || '').trim();
  if (explicit) return explicit;
  const enabled = (process.env.AIFACTORY_ENABLE_DEFAULT_CSP || '').toLowerCase();
  if (enabled === '1' || enabled === 'true' || enabled === 'yes') {
    return DEFAULT_FRONTEND_CSP;
  }
  return null;
}

export function applySecurityHeaders(headers: Headers): void {
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('X-Frame-Options', 'DENY');
  headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  const csp = resolveFrontendCsp();
  if (csp) headers.set('Content-Security-Policy', csp);
  const hstsOn = (process.env.AIFACTORY_ENABLE_HSTS || '').toLowerCase();
  if (hstsOn === '1' || hstsOn === 'true' || hstsOn === 'yes') {
    let hsts = 'max-age=31536000; includeSubDomains';
    const preload = (process.env.AIFACTORY_HSTS_PRELOAD || '').toLowerCase();
    if (preload === '1' || preload === 'true' || preload === 'yes') {
      hsts += '; preload';
    }
    headers.set('Strict-Transport-Security', hsts);
  }
}
