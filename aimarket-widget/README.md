# AIMarket Widget v2.0.0

**Embeddable AI capability search + invoke widget. One `<script>` tag.**

## Value in plain words

Drop a search-and-buy box for AI capabilities onto any website — visitors discover and invoke marketplace skills without leaving your product.

**Простыми словами:** Вставляете на любой сайт блок «найти и купить» AI-возможности — посетители находят и вызывают навыки маркетплейса, не уходя с вашего продукта.

Full text: [docs/value.md](docs/value.md)

## Killer feature — 1-Click Agent Embed

**~60 seconds to production.** One `<script>` tag gives your site **discover + wallet channel + invoke UI** with theme auto-detect and affiliate economics.

| | |
|---|---|
| **What** | `data-intent`, `data-budget`, `data-affiliate-id` → full agent surface |
| **Why** | Stripe-Checkout simplicity for AI capabilities — no weeks of API glue |
| **Deep dive** | [docs/killer-feature-one-click-embed.md](docs/killer-feature-one-click-embed.md) · [Ecosystem killer features](../docs/killer-features.md) |

## Live Demo

**[modelmarket.dev/widget/demo](https://modelmarket.dev/widget/demo)** — interactive demo with all 6 themes

**[modelmarket.dev/live](https://modelmarket.dev/live)** — AI Economy live ticker (Bloomberg Terminal)

## Quick Start

```html
<script src="https://modelmarket.dev/widget/widget.js"
        data-theme="auto"
        data-intent="translate to 5 languages"
        data-budget="3.00"
        data-hub-url="https://modelmarket.dev"
        data-affiliate-id="my_blog"></script>
```

## Themes

| Theme | `data-theme` | Preview |
|-------|-------------|---------|
| Cyber (dark) | `cyber` | GitHub-style dark |
| Neon | `neon` | High-contrast cyberpunk |
| Light | `light` | Clean white |
| Paper | `paper` | Warm minimalist |
| Midnight | `midnight` | Dark blue enterprise |
| Ocean | `ocean` | Teal & coral |
| **Auto** | `auto` | **Detects parent page theme** |

`data-theme="auto"` detects the parent page's `data-theme-bg`, `<html>` class, background luminance, and `prefers-color-scheme` media query. Switches live when system theme changes.

## Affiliate Program

Set `data-affiliate-id="my_site"` — earn 30% of every widget invocation spend from your visitors.

## Security

- **No inline event handlers** — all events via `addEventListener`. XSS-safe.
- **Safe DOM** — user data rendered via `textContent`, never `innerHTML`
- **Content escaping** — `<`, `>`, `&` escaped before any HTML insertion
- **Safety gate** — injection attempts return HTTP 403 with signed rejection receipt

## API

The widget calls the hub's v2 API:

| Call | Endpoint |
|------|----------|
| Search | `GET /ai-market/v2/search?intent=...&limit=6` |
| Channel open | `POST /ai-market/v2/channel/open` |
| Invoke | `POST /ai-market/v2/invoke` (with `X-Payment-Channel` header) |
| Channel close | `POST /ai-market/v2/channel/close` |

## License

MIT — see [LICENSE](LICENSE).

## Governance

| Doc | Purpose |
|-----|---------|
| [LICENSE](LICENSE) | MIT terms |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CONTRIBUTORS.md](CONTRIBUTORS.md) | Maintainers & recognition |

Maintained by AI-Factory · [Demo](https://modelmarket.dev/widget/demo) · [Live Stream](https://modelmarket.dev/live) · [Hub](https://modelmarket.dev)
