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

## Contents (19 chapters + Q&A)

1. Cosmic thesis & ideology (Factory · Hub · Mesh · Oracles · **GAIA** · **ATLAS** · **SKOPOS** · **Metis** · **MOMUS** · **LOGOS** · Chain · ARGUS)
2. Galaxy map (live surfaces, ecosystem diagram)
3. Planet Factory (13-agent pipeline)
4. AIMarket Hub (protocol, plugins, invoke flow)
5. Oracle constellation (×17 math)
6. ARGUS — human touchpoint
7. ACEX, Lottery, Base mainnet contracts
8. Desktop SKUs, widget, SDKs
9. AI Service Mesh
10. Alien Monitor & Pulse Terminal
11. Architecture views (ports, supply/demand)
12. Base deployment guide
13. **GAIA** — Earth's whisperers (physical relays, LIVE provenance)
14. **ATLAS** — living map (LIVE vs SIM, Analyst, screenshots)
15. **SKOPOS** — watchtower (nginx/Apache fleet + Security Center)
16. **Metis** — thinking gate (fail-closed cognitive verify)
17. **MOMUS** — honest accuser (red team + Treasury separation of duties)
18. **LOGOS** — read-only federation observatory (snapshots, anomalies, insights)
19. **HELIOS & DIOSCURI** — storytellers of the fleet
20. Q&A Oracle (operators, developers, end users) — includes ATLAS/GAIA/SKOPOS/Metis/MOMUS/LOGOS

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
# After editing content/*.json (or re-running the constellation expander):
python3 docs/encyclopedia/scripts/expand_constellation.py   # idempotent GAIA/ATLAS/SKOPOS/Metis/MOMUS/LOGOS/HELIOS chapters
node docs/encyclopedia/scripts/generate-encyclopedia.mjs all
node docs/encyclopedia/scripts/generate-pdf.mjs all          # en/ru/es
```

## Source content

Editable JSON: `content/{en,ru,es,fr,zh}.json`  
Shared product shots: `assets/screenshots/shared/` (ATLAS map/analyst, SKOPOS banner/analytics)  
Styles: `shared/encyclopedia.css`
