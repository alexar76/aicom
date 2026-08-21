# Handoff — what is left on modelmarket.dev

State as of 2026-07-27, 20:30 UTC, every line below verified against the live hub and the
live registries rather than from notes. Everything that remains needs a credential, a
wallet, or a release decision — that is the only reason it is here and not done.

Background: [`payment-enable-runbook.md`](payment-enable-runbook.md) for how payments were
turned on, [`onchain-journal.md`](onchain-journal.md) for contract addresses and on-chain
proofs.

---

## Live state — verified, no action needed

```
https://modelmarket.dev/.well-known/ai-market.json
  payment_configured   true          ← Base mainnet, real USDC
  channels.demo_mode   false
  capabilities         5 local / 16 total, all 16 executable
  mcp_endpoint         /ai-market/mcp   (market_search, market_invoke)
  image                modelmarket-hub:prod-20260727-fulfillment
```

Escrow is the only funding path. The `tx_hash` verifier lives in
`web.backend.services.ai_market_protocol.on_chain`, which `aimarket-hub/Dockerfile` does
not copy into the image — no env var changes that. A `tx_hash` open will always answer
`on-chain verification unavailable`; that is correct behaviour, not a bug to chase.

---

## 1. External depositor proof — DONE (2026-07-27)

Depositor `0x6E94…6C9c` (not the hub) funded \$1 USDC escrow, bought
`skopos.security.posture@v1` @ \$0.08, and received \$0.92 on-chain refund.
Full tx table: [`onchain-journal.md`](onchain-journal.md) §3j.

Settle txs: debit [`0xf740cd…`](https://basescan.org/tx/0xf740cd0cd2ada97dd243ad067c2dc0f16504d40030c54b4aef37137f2a824355),
settle [`0xcce0dc…`](https://basescan.org/tx/0xcce0dcdddfd962cd2d16840246cfc2761b8325d4a58f186009bcdd5b3c942472).

---

## 2. Registry publishes — DONE, all four

Sources already point at `https://modelmarket.dev`. Versions in tree vs what users
actually install, checked against each registry API:

| Registry | In tree | Published | State |
|---|---|---|---|
| **pub.dev** `aimarket_agent` | 0.2.1 | **0.2.1** | ✅ published 2026-07-27 20:21 UTC |
| **npm** `@aimarket/agent` | 0.2.1 | **0.2.1** | ✅ published 2026-07-27 20:28 UTC |
| **crates.io** `aimarket-agent` | 0.2.1 | **0.2.1** | ✅ published 2026-07-27 20:37 UTC |
| **PyPI** `aimarket-agent` | 2.1.2 | 2.1.1 | no `~/.pypirc` / needs `PYPI_API_TOKEN` |

Verified against each registry's API, and against the artifacts themselves rather than
the version numbers: the npm tarball contains no `aicom.io` at all, and the pub.dev
archive's single occurrence is the CHANGELOG line describing the fix — `lib/` is clean.
The correction reached users, not just the version string.

**Token hygiene, still outstanding.** An npm token was pasted into a chat transcript
during this work. Revoke it at <https://www.npmjs.com/settings/~/tokens> and use an
Automation token for future releases. Same for any crates.io token that was handled the
same way (<https://crates.io/settings/tokens>).

pub.dev has nothing to revoke — it issues no API tokens. Publishing rights come from an
OAuth grant to your Google account, stored in `~/Library/Application
Support/dart/pub-credentials.json`. `dart pub logout` clears it on one machine; killing
it everywhere means revoking the `pub` app under Google Account → Security → third-party
access; and who may publish at all is the uploaders list on
`pub.dev/packages/aimarket_agent/admin`.

Users who already saved a `hub_url` / `ai_base_url` in their local config keep the old
host regardless of the version they upgrade to. Worth one line in the release notes.

---

## 3. Desktop binaries — a decision, not a blocker

Ten SKUs under `desktop-integrations/` plus `coach` still ship binaries that point at
`hub.aicom.io`, a domain that is not ours. The source is fixed; the artifacts are not.

The toolchain is present on the build machine and clean — Flutter 3.41.4 stable at
`~/flutter/bin` (not on `PATH`, hence an earlier report that it was missing), Xcode 26.3,
Android SDK 36.1.0, `flutter doctor` reports no issues. The shared default lives in
`desktop-integrations/packages/aicom_desktop_core/lib/src/dev_wallet.dart`;
`local-security-audit` also carries it inline in `src-tauri/src/main.rs`.

So this is waiting on someone deciding to cut releases, not on tooling.

---

## Done in this pass — context, not work

- **Payments live.** Found the prod `.env` pointing `AIMARKET_PAYMENT_RECIPIENT` at Anvil
  account #0 (public private key) with crypto on and mainnet enabled; the verify-stub was
  the only thing between that and real USDC. Recipient is now `0x1218`, contract and
  escrow both `0x0606983c…72C25D`. Anvil/Hardhat addresses are blocklisted in
  `security/prod_startup_guard.py` **and** `aimarket_hub/config.py` — the standalone hub
  image does not ship the `security` package, so one copy would not have covered it.
- **Catalogue is honest.** Was 17 advertised / 5 executable: twelve seeded rows priced
  $0.15–$1.50 answered 404, and a name-pattern cleanup had missed all of them because
  they were named respectably. `aimarket_hub/fulfillment.py` now gates search, manifest,
  `.well-known` counts and factory ingest on whether a row can actually run.
  `include_demo=true` does not override it. Now 16 / 16.
- **MCP gateway** at `/ai-market/mcp`, `local-security-audit` wiring, security-rules feed.

---

## Operational notes — do not relearn these

- **Deploy** by rsyncing to `/root/aicom-hub-build` and `docker build -f
  aimarket-hub/Dockerfile`. **Never `git pull` in `/root/claudecode/aicom`** — it sits on
  `a42aa97a` with hand-fixes to `alien-monitor/` and `apps/pulse-terminal/` that incoming
  commits touch.
- **`AIFACTORY_PROD=1` is a per-container `-e` flag**, never a line in the shared `.env`.
  Four other services read that file and `aicom-app` ships the `security` package, so the
  full guard would refuse its next start over SQLite and LLM-key findings unrelated to
  payments.
- Live hub runs `AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG=0` because factory products with an
  `invoke_url` carry no `provider_pubkey`. Re-enable once they sign.
- **Rollback:** image `modelmarket-hub:prod-20260726-a42aa97adc`, env backup
  `/root/claudecode/aicom/.env.bak-20260727-204713`, DB backup
  `hub.db.bak-20260727-fulfillment` inside the hub volume. Setting
  `AIFACTORY_PAYMENT_VERIFY_STUB=1` and restarting takes payments offline without
  touching open channels.
- **88 commits are unpushed** on `main` (11 from this work, `d97da4d5`…`f7bb75a1`; the
  other 77 predate it). Left that way deliberately — nothing here has been pushed.
