# Pulse Terminal

**Premium capital-markets dashboard** for [ACEX](https://github.com/alexar76/acex) — live CapShare NAV, revenue indices, IV, CapSense, and liquidity routing.

<p align="center">
  <strong>Bloomberg-grade terminal UX · WebSocket-first · ACEX Protocol v0.2</strong>
</p>

## Features

- **Live feed** — WebSocket → SSE → polling fallback (`pulse_terminal.refresh_ms` from API)
- **Ticker strip** — scrolling capability revenue indices
- **Listings grid** — CapShare NAV, IV badges, trust gauges, SVG sparklines
- **Detail rail** — index components, CapSense series, liquidity mesh JSON
- **Chain lens** — `any` · `evm` (Pulse AMM) · `solana` (Jupiter)

## Quick start (dev)

```bash
# Terminal 1 — factory API (port 9081)
./run-compose.sh

# Terminal 2 — Pulse Terminal UI
cd apps/pulse-terminal
npm install
npm run dev
```

Open [http://localhost:5199](http://localhost:5199)

## API

| Feed | Endpoint |
|------|----------|
| Snapshot | `GET /api/v2/capital/pricing` |
| SSE | `GET /api/v2/capital/pricing/stream` |
| WebSocket | `WS /api/v2/capital/pricing/ws` |
| Hub alias | `GET /ai-market/v2/capital/pricing` |

Query: `chain=any|evm|solana`, `listing_id`, `limit`.

## Production

```bash
cd apps/pulse-terminal
docker build -t pulse-terminal .
docker run -p 5199:80 pulse-terminal
```

Set `VITE_PULSE_API_URL` at build time if API is on another origin.

## Electron (optional)

Web build is Electron-ready — wrap `dist/` with `electron-builder` and point at the same API URL.

## Stack

Vite · React 19 · Tailwind · TypeScript · native WebSocket/SSE

## License

MIT — part of ACEX / AI-Factory ecosystem.
