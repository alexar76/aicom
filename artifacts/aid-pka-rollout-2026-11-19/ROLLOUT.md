# AID endpoint proof on modelmarket.dev/mcp — rollout 2026-11-19

Owner 19.11: «Yes, build it», then «ну давай сразу сделаем чтобы подпись заработала а потом напишем». Context:
Balázs Nemethi (AID, agentcommunity.org) asked on dawn@ietf.org for an ARD implementation to be the other side
of an ARD + AID interop test; modelmarket.dev serves ARD since 2026-11-04 and is that domain.

## What changed

`aimarket_hub/aid_pka.py` (new), one call in `hub_routes/ard.py`, `Signer.derived_ed25519_seed` in `signing.py`
(aicom main). `/mcp` answers AID v2.1.1 Appendix B proof requests: `Signature-Input` / `Signature` (Ed25519,
RFC 9421, 60 s) and `Cache-Control: no-store`, with domain binding (`AID-Domain`) for modelmarket.dev; any other
domain gets 403 without a signature. Requests without `Accept-Signature` are unchanged. The key is derived from the
hub signing key with HKDF-SHA256, info `aimarket-hub/aid-pka-v2`.

- `k` = `H_pv7n0l5b3o5SgCFPaAhm-K1flFG-Dim16mHmclqaM`
- keyid (RFC 7638) = `GPgQ1hgsCNYND5UeXKXx970ljHR9Tlg4dR1oMK-p9aA`
- computed in a throw-away container from the new image (no network, the key copied to tmpfs, only the public
  values printed).

## Checks before

- tests/test_aid_pka.py 22 passed (verifier written from the spec text, RFC 8037 A.3 thumbprint vector); ARD, MCP
  gateway, AI catalog and signing tests 194 passed.
- The AID reference verifier (PyPI aid-discovery 2.1.1, `aid_py/pka.py`) was read line by line against the
  signer: same covered set and order, same six parameters (`created`/`expires` bare integers), the base built
  from the received `@signature-params`, `@target-uri` normalised as scheme + lowercase host without default
  port + path + query, `Cache-Control: no-store`, standard base64 in `Signature`. Running it was refused by the
  auto-mode classifier (downloaded code), so it was not executed.
- Open alerts read first (skopos-vps): nothing on factory-vps; attested disk filling (not this host).
- The running `modelmarket-hub` files `hub_routes/ard.py` and `signing.py` = the 3.21.0 release files (sha256
  a48223ca15d4db3a…, 5fbd626b352eb8dd…); the overlay copies differ only by the AID lines (`git diff ce215c70b`).

## Kit

`kit/build.sh` (refuses unless the running files are the 3.21.0 ones; image FROM the running one, three files
replaced, import checked from `/app`), `kit/roll.sh` (SQLite backup, then `rollout_container.py`, which restores
the previous container and THEMIS if a health URL fails), `verify_live.py` (outside check, `cryptography` only).
Health URLs: http://127.0.0.1:9083/ai-market/v2/health and http://127.0.0.1:9460/health (THEMIS shares the hub's
network namespace).

Image `modelmarket-hub:3.21.0-aidpka-20261119` = sha256:f4149f51b9bc…, FROM `aidpka-base-modelmarket-hub:20261119`
= sha256:fd24ce8e09e2… (the image the hub ran).

## Switch

| hub | host, unit | switched (UTC) | new image | previous (rollback) | database backup |
|---|---|---|---|---|---|
| modelmarket.dev | factory-vps, `modelmarket-hub` (THEMIS recreated in its namespace) | 2026-11-19 07:28:04 | `modelmarket-hub:3.21.0-aidpka-20261119` | `modelmarket-hub-security-prev-1795073285144252844`, THEMIS `themis-security-prev-1795073285144252844`; snapshot `/root/security-rollbacks/modelmarket-hub-1795073285144252844/inspect.json` | `/root/hub-backups/modelmarket-hub-pre-aidpka-20261119T072804Z.db` (6.3M) |

Rollback: `cd /root/aidpka-rollout-20261119/kit && python3 rollout_container.py modelmarket-hub --rollback`. Nothing in
the database needs undoing (no migration). Then remove `k=` from the `_agent.modelmarket.dev` TXT record, or every
AID client fails the proof.

## After

- `verify_live.py` from skopos-vps (clock in UTC, cryptography 41.0.7), 07:28:46Z: unbound ok, bound to
  modelmarket.dev ok, unserved domain → 403 without signature. From the Mac the same run flagged only freshness:
  the Mac clock runs ~58 min ahead.
- Plain `GET /mcp` 200, MCP `initialize` 200, health, `/.well-known/ard.json`, `/` 200; THEMIS healthy.
- Hub log since the switch: one line, an outside peer's `/.well-known/ai-market.json` 404 during the crawl (not
  this change).
- DNS: owner to put `k` into `_agent.modelmarket.dev` (Timeweb):
  `v=aid2;u=https://modelmarket.dev/mcp;p=mcp;a=none;s=AIMarket hub: search and call agent tools;k=H_pv7n0l5b3o5SgCFPaAhm-K1flFG-Dim16mHmclqaM`
  (139 bytes).
