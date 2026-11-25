# Actor proof v2 on attested — prepared 2026-11-25, APPLIED 2026-11-25 04:08:54–04:09:25Z

## Why

main has carried request-bound actor proofs since c3e0fa82e (2026-10-25): the signature covers the
destination, method, path, query and SHA-256 of the body, and spent nonces are stored in each
service's database. The attested host never got it. Every Attested service there still verifies the
v1 message `<actor id>\n<timestamp>\n<nonce>`, so a captured header set can be replayed against a
different request for five minutes.

The published Python client is already on v2: `attested-memory` 0.2.0 (PyPI, 2026-11-03) signs
`attested-actor/v2…`. Against prod it gets 401 on every call (confirmed 2026-11-25: the prod gateway
verifies the v1 message at `saas_gateway/app.py:661`). Applying this kit fixes that client.

## What changes

| Service | Now | After |
| --- | --- | --- |
| memory-market (hub compose) | `attested-memory-hub-memory-market:atlas-20261124` | `…:actorv2-20261125` (main's package + static) |
| aicom-saas-gateway-1 | `aicom-security:aicom-saas-gateway-1-hc-live-20261031` | `aicom-security:aicom-saas-gateway-actorv2-20261125` |
| aicom-personal-memory-1 | `…personal-memory-1-hc-live-20261031` | `…personal-memory-actorv2-20261125` |
| aicom-team-memory-1 | `…team-memory-1-hc-live-20261031` | `…team-memory-actorv2-20261125` |
| aicom-expert-market-1 | `…expert-market-1-hc-live-20261031` | `…expert-market-actorv2-20261125` |
| attested-saas-deal/meter/prove-1 | `…-signature-20261108t073311z` | `…-actorv2-20261125` |
| /opt/aicom/saas-landing | v1 `actor.js` | main's actor.js, checkout.js, developer.js, memory.js, team.js, developers.html |

Each image is the running image plus main's package copied over site-packages (`kit/<svc>/Dockerfile`),
built on attested 2026-11-25 from main 3e7c911ab. Prod-vs-main diffs were read for every package:
the only prod-side lines main lacks are the v1 verifier itself. Main additionally brings, from the
same 10-25 commit, the Deal/Meter/Prove and gateway checkout fixes (an Idempotency-Key or invoice
that belongs to another checkout is refused; confirmation and credit in one transaction) and the
team-tag LIKE escape.

Schema: each service creates `actor_proof_nonces_v2` (`CREATE TABLE IF NOT EXISTS`) at startup.
Additive; the rollback leaves it.

Not changed: hub, truth-layer, provenance-ledger, edge (Caddyfile is identical to main; no inline
script changed, so the CSP hashes stay valid).

## Checks done before writing this

- Tests on main: deal 57, meter 57, prove 62, gateway 10, expert 16, personal 2, team 2,
  memory-market 28, Python client 11, cross-service (proxy flow + browser contract) 5. All pass.
- Isolated staging on attested (own Postgres in tmpfs, throwaway secrets, no hub, no ledger,
  no payment adapter; edge = prod edge image + prod Caddyfile + prod landing with the six new files),
  through an SSH tunnel:
  - PyPI `attested-memory` 0.2.0: trial 201, write, read, search all OK;
  - same proof twice: second 401 "actor proof already used";
  - a proof for one query sent with another: 401 "actor intent does not authorize…";
  - v1 headers: 401;
  - browser /memory: trial, write (Unicode body), search with a Cyrillic query: 201/201/200, no console errors;
  - browser /teams: trial, create team, team write, team search: 201/201/201/200.
  The staging stack and its secrets were removed afterwards.
- Deal/Meter/Prove overlay images start (healthz 200, audiences attested-deal/-meter/-prove).
- `rollout_container.py --dry-run` for all seven swapped containers: no env names dropped, no borrowers.

## Apply

On attested, as root (kit is at /root/actorv2-kit-20261125, images already built):

    /root/actorv2-kit-20261125/apply.sh

About two minutes. During that window a browser holding the old pages, or any v1 caller, gets 401;
a reload fetches the new pages. The script prints the backup folder.

Note: `/opt/aicom/saas-compose.yml` builds gateway/personal/team/expert from the host source trees,
which are older than main. A plain `docker compose up` there would bring back v1 (that was already
true for the 10-31 images). Use `rollout_container.py` for those four.

## Verify after apply

- `docker ps` shows the eight `actorv2-20261125` images healthy;
- PyPI client 0.2.0 against https://attestedmemory.net: `keys/me` / search answer, not 401
  (needs a key: an existing test key, or a trial with the owner's OK);
- open https://attestedmemory.net/memory and /teams, use the existing key, search;
- `docker logs --since 10m` for each: no tracebacks.

## Rollback

    /root/actorv2-kit-20261125/rollback.sh /root/actorv2-backup-<stamp>

Restores the hub compose (memory-market back to atlas-20261124), swaps the seven containers back to
their previous images, restores the attested/deploy compose and the six page files.

## Applied 2026-11-25 04:08:54–04:09:25Z (owner: «Yes, apply»)

Backup: `/root/actorv2-backup-20261125T040854Z`. Previous containers kept stopped as
`<name>-security-prev-17955797…` (gateway, personal, team, expert, deal, meter, prove).

Checked right after, against prod:

- all eight `actorv2-20261125` containers healthy; no tracebacks or 5xx in their logs for 10 minutes;
- memory-market `/v1/catalog` with the service key: v2 proof 200; the same proof again 401 "actor proof
  already used"; a proof for `q=x` sent with `q=secret` 401 "actor intent does not authorize…"; v1 proof 401
  "request-bound actor proof v2 is required…"; no actor headers 200 (public catalog);
- https://attestedmemory.net/actor.js serves the v2 signer; /, /memory, /teams, /developers, deal/meter/prove
  healthz and the memory manifest answer 200.

Packages: nothing to release. The PyPI `attested-memory` 0.2.0 wheel's code is byte-identical to main's
client (diff of the unpacked wheel, 2026-11-25); it starts working against prod with this rollout. The services
are not on PyPI. Not checked live: the PyPI client end-to-end on attestedmemory.net (needs a key; covered on staging).
