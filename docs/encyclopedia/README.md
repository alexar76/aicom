# AICOM Cosmic Encyclopedia

Premium storybook-style guide to the AICOM federated autonomous-agent economy.

## Formats

| Language | HTML | PDF |
|----------|------|-----|
| English | [en/index.html](./en/index.html) | [pdf/aicom-encyclopedia-en.pdf](./pdf/aicom-encyclopedia-en.pdf) |
| Русский | [ru/index.html](./ru/index.html) | [pdf/aicom-encyclopedia-ru.pdf](./pdf/aicom-encyclopedia-ru.pdf) |
| Español | [es/index.html](./es/index.html) | [pdf/aicom-encyclopedia-es.pdf](./pdf/aicom-encyclopedia-es.pdf) |
| Français | [fr/index.html](./fr/index.html) | — |
| 中文 | [zh/index.html](./zh/index.html) | — |

**Portal:** [index.html](./index.html) — language picker + PDF links.

## Contents (12 chapters + Q&A)

1. Cosmic thesis & ideology
2. Galaxy map (live surfaces, ecosystem diagram)
3. Planet Factory (13-agent pipeline)
4. AIMarket Hub (protocol, plugins, invoke flow)
5. Oracle constellation (×17)
6. ARGUS — human touchpoint
7. ACEX, Lottery, Base mainnet contracts
8. Desktop SKUs, widget, SDKs
9. AI Service Mesh
10. Alien Monitor & Pulse Terminal
11. Architecture views (ports, supply/demand)
12. Base deployment guide
13. Q&A Oracle (operators, developers, end users)

## Screenshots

Localized UI screenshots per language live in `assets/screenshots/{en,ru,es,fr,zh}/`
(`fr`/`zh` currently reuse the English captures until localized UI shots are taken).  
Language-neutral ecosystem visuals: `assets/screenshots/shared/`.

Refresh screenshots:

```bash
node docs/encyclopedia/scripts/capture-locale-fast.mjs
```

## Rebuild

```bash
node docs/encyclopedia/scripts/generate-encyclopedia.mjs all
node docs/encyclopedia/scripts/generate-pdf.mjs all
```

## Source content

Editable JSON: `content/{en,ru,es,fr,zh}.json`  
Styles: `shared/encyclopedia.css`
