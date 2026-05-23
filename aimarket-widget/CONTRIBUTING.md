# Contributing to AIMarket Widget

Thanks for helping improve the embeddable widget. The project is **vanilla JavaScript + CSS + static HTML** — no bundler required.

## Quick start

```bash
git clone https://github.com/alexar76/aimarket-widget.git
cd aimarket-widget
python3 -m http.server 8765
# Open http://localhost:8765/demo.html
```

Point `data-hub-url` at a running [AIMarket Hub](https://github.com/alexar76/aimarket-hub) (default dev: `http://127.0.0.1:9080`).

## What to contribute

| Area | Files |
|------|--------|
| Widget core | `widget.js` |
| Themes | `themes.css` |
| Demos | `demo.html`, `live-stream.html` |
| Docs | `README.md`, `docs/` |

Good first issues: theme tweaks, accessibility (ARIA/keyboard), error messages, hub API compatibility, demo polish.

## Pull request checklist

1. **Scope** — one logical change per PR (feature, fix, or docs).
2. **Security** — no `innerHTML` with user/hub data; use `textContent` / safe DOM APIs (see [SECURITY.md](SECURITY.md)).
3. **Themes** — if you add a theme, document it in README and add a demo toggle in `demo.html`.
4. **Hub contract** — widget uses AIMarket Protocol v2 (`/ai-market/v2/search`, `/invoke`, `/channel/*`). Do not break attribute names without a major version bump.
5. **Manual test** — run `demo.html` against a hub; note results in the PR description.
6. **DCO** — sign off every commit: `git commit -s -m "..."`.

## Code style

- ES5-compatible IIFE in `widget.js` (no transpiler in production embed).
- 2-space indent, double quotes in JS unless matching surrounding block.
- Prefer `addEventListener`; never inline `onclick=` in generated markup.

## Security issues

Do **not** open public issues for vulnerabilities. Email **security@aicom.io** — see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
