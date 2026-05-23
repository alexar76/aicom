# Security Policy — aimarket-widget

## Reporting a Vulnerability

**Do not open a public issue for security bugs.**

Email: **security@aicom.io**

We acknowledge within 48 hours and share a fix timeline.

## Scope

- **`widget.js`** — embed script, DOM rendering, hub API calls, payment channel headers, affiliate attribution
- **`themes.css`** — theme tokens loaded into host pages
- **`demo.html` / `live-stream.html`** — official demo pages shipped with the widget
- **XSS / injection** — any path where hub responses or URL/query attributes reach the DOM unsafely
- **Open redirect / SSRF** — unsafe `data-hub-url` or fetch targets (widget should only call configured hub origins)

## Out of Scope

- Vulnerabilities in the upstream AIMarket Hub or factory backend (report to hub maintainers)
- Host site CSP misconfiguration on third-party sites embedding the widget
- Social engineering or phishing using copied widget assets
- Issues requiring physical access to an end-user machine

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` (v2.x) | yes |
| v1.x tags | best effort |

## Safe embedding practices (for integrators)

- Serve `widget.js` over **HTTPS**
- Set an explicit **`data-hub-url`** you trust
- Use a strict **Content-Security-Policy** on your site; allow connect-src to your hub only
- Do not pass unsanitized HTML into `data-intent` from untrusted users without review

## Disclosure

Coordinated disclosure preferred. We credit researchers in release notes when permitted.
