# AIMarket Hub 3.16.2 — mandates with an owner's approval, A2A webhooks, and the October security line

```bash
pip install aimarket-hub==3.16.2
```

The last GitHub release was v3.2.1 (2026-08-12); PyPI has shipped every version since. What the hub gained between 3.2.1 and 3.16.2, by date:

- **3.16.0 (2026-10-20)** — a mandate can require its owner's approval above a threshold; A2A tasks push their state to the client's webhook; owner notifications over Telegram; the deposit-watch RPC list rotates and is checked (`rpc-check`) instead of relying on one node; `/clients` serves the PyPI wheel; the 3.16.0 wheel is installed on all six public hubs.
- **Security, 2026-10-25/26** — secret exports and signing identities hardened, published keys quarantined, release secret gates tightened, signing-identity warnings and provenance key validation preserved; a reverse proxy on the same host is no longer treated as "this machine" (the same-host proxy check the whole ecosystem adopted); the hub's channel race that lost debits is fixed, and the Hub API module is split (1,441 → 801 lines) with request guards and peer routing in their own files.
- **3.16.1 / 3.16.2 (2026-10-28/29)** — funded oracle calls are authenticated for paid tiers; EMPORION is renamed **SYMMARTYS** with counterparty verification; docs link to satellites through URLs the public mirrors serve; aimarket-provenance 2.3.1 released alongside.

Free trial for strangers is unchanged: send `X-AIMarket-Sandbox-Visitor` with a stable id and no payment, get a signed receipt; the terms are published in `/.well-known/ai-market.json` (`free_trial`).

Full history: the monorepo [aicom](https://github.com/alexar76/aicom) `aimarket-hub/` commits.
