# Multica agent egress allowlist — attested, 2026-11-04

Owner: «Закрыть исходящий трафик», then «Что осталось — все по очереди делай». Times are server clocks (UTC).

## Why

The agent runtime `multica-daemon` (OpenCode + DeepSeek) carries the agent's secrets in its environment
(`DEEPSEEK_API_KEY`, `GH_TOKEN`, `TELEGRAM_BOT_TOKEN`, and since today `AIMARKET_API_KEY` with a $5 balance) and reads
other people's text from GitHub, HN and lobste.rs. It sat on the compose network `multica_app` with an open route out:
a prompt injection could send any of those secrets anywhere. The domain list existed only in the prompt.

## What changed (12:12Z)

- New service `egress` (`multica-egress:20261104`, built in `/opt/multica/egress` from `ubuntu:24.04` + apt
  `tinyproxy` 1.11.1): `FilterDefaultDeny`, anchored host regexes in `egress/allow`, CONNECT only to 443, clients only
  from the agent subnet. Read-only root, `cap_drop: ALL`, no-new-privileges, 128 MB, 0.5 CPU, non-root.
- New compose network `agent`: `internal: true`, subnet `10.250.0.0/24` (unused on the host; `172.31.250.0/24`
  collided with the lottery network). Members: `multica-daemon`, `multica-backend-1`, `multica-egress`.
- `daemon` moved from `app` to `agent` only, with `HTTPS_PROXY`/`HTTP_PROXY` (both cases, because curl reads only
  lowercase `http_proxy`) = `http://egress:8888` and `NO_PROXY=backend,localhost,127.0.0.1`.
- `backend` additionally joins `agent` so the daemon still reaches it.
- Applied with `docker compose up -d --no-build egress backend daemon` while no task was running; postgres, frontend
  and gateway were not touched. Old compose file: `/opt/multica/docker-compose.yml.bak-20261104-egress`.

Allowed hosts (`egress/allow`): `api.deepseek.com`, `models.dev`, `github.com`, `api.github.com`, `hn.algolia.com`,
`news.ycombinator.com`, `hacker-news.firebaseio.com`, `lobste.rs`, `api.telegram.org`, `hub.attestedmemory.net`.

## Checked from inside the daemon

- `https://example.com` through the proxy → `403 Filtered` (python urllib reports `Tunnel connection failed: 403
  Filtered`); `http://example.com` → 403 from the proxy; `https://1.1.1.1` without the proxy → no route;
  `getent hosts example.com` → no answer (an internal network gets no outside DNS, so DNS is not a side channel).
- `api.github.com` 200, `api.deepseek.com` 401 (no key sent), `api.telegram.org` 302, the hub health 200,
  `models.dev` 200, `hn.algolia.com` 200, `lobste.rs` 200, `gh api rate_limit` works, `http://backend:8080/health`
  200, `opencode mcp list` → aimarket connected, the runtime shows online.
- Agent task MY-52 through Multica (DeepSeek → MCP memory.search → `gh`): done, correct answer, $0.004.
- Refused and left refused: `models.opencode.ai` (OpenCode's own catalogue; the cached one is used) and
  `registry.npmjs.org` (package installs/update checks — too wide a channel). The agent works without both.

## What it does not cover

The allowed hosts are still channels: an injected agent could put a secret into a GitHub request, a Telegram message
or a **public** Attested Memory record. The instructions forbid it; nothing technical does. `GH_TOKEN` scopes were
not checked (reading them was refused as credential handling). DeepSeek sees everything the agent reads anyway.

## Rollback

```bash
ssh attested 'cd /opt/multica && cp docker-compose.yml.bak-20261104-egress docker-compose.yml && docker compose up -d --no-build backend daemon && docker rm -f multica-egress && docker network rm multica_agent'
```

To allow one more host: add an anchored line to `/opt/multica/egress/allow`, `docker compose build egress`,
`docker compose up -d --no-deps egress`.

## Later the same day

- `^modelmarket\.dev$` added for the mystery shopper (12:2xZ), egress rebuilt and recreated alone.
- `/opt/multica/set-secrets.sh` now recreates the daemon with `--no-deps`: without it the compose dependencies
  (postgres, backend, and now egress) were recreated too, as happened at 10:13Z. Its KEYS list gained
  `AIMARKET_API_KEY` and `AIMARKET_SHOPPER_API_KEY`. Copy of the original: `set-secrets.sh.bak-20261104`.
- Mystery shopper prepared, not running: Multica agent «тайный покупатель» (id 12c0431e-2dae-437d-b097-1a889e91263c,
  same runtime and model as вжик, instructions in `/root/memory-owner-20261104/shopper-instructions.txt` on attested),
  autopilot «Тайный покупатель: проверка рынка» (bbbc9980-b83d-4f27-b706-0efe206ae049) with no trigger, MCP
  `modelmarket` → https://modelmarket.dev/mcp with `{env:AIMARKET_SHOPPER_API_KEY}`, account
  `acct_50f72ba01ddfff96` on modelmarket.dev ($0.01 signup grant). Funding it and listing it in modelmarket.dev's
  `ecosystem.json` were refused by the auto-mode classifier as a change to a shared resource → owner's decision.
- Receipts through MCP: the hub omits the ML-DSA part (`pq_value_omitted_chars`), so `/receipts/verify` answers
  `valid: false`, `classical_valid: true`, `signer_matches_live_key: true` (checked on the attested hub). The shopper's
  instructions treat that as normal.
- 12:2x–12:35Z, owner «Да, запускай» / «Всех, запускай»: operator credit $5 on modelmarket.dev
  (`acct_50f72ba01ddfff96`, balance $5.01); daily trigger 0 9 * * * UTC (first set as 0 12 Europe/Moscow, moved to UTC on the owner's rule «расписание всегда только по UTC»; next 2026-11-05 09:00Z);
  manual run MY-53: 2 calls (gaia.weather.read via iot.modelmarket.dev, symmartys.fx.rate), $0.002, both OK, report
  sent to Telegram through the proxy. It found that `/receipts/verify` is a self-verifier: receipts issued by a
  provider (`issuer` = provider URL, own `public_key`) never pass it — not a seller fault. The response's
  `verify_url` (AWR work receipt, `/ai-market/v2/p/provenance/verify/urn:uuid:…`) is the check; instructions updated.
  The modelmarket.dev `ecosystem.json` entry for the shopper is prepared and checked
  (`/root/shopper-20261104/ecosystem.after.json` on factory-vps, 8 self accounts) but installing it was refused
  by the auto-mode classifier → the owner installed it at 12:36:57Z (colleague-tasks §64 step 3); the hub reloaded the
  policy at 12:37:06Z (8 self accounts) and all three shopper calls so far read `operator_self` / basis `account`.
- `AIMARKET_BUYER_SALT` deliberately left unset: since the buyer-ref fix nothing keys data by the channel reference,
  and the peer-facing `X-AIMarket-Buyer` id is meant to change with the process (unlinkable over time).
