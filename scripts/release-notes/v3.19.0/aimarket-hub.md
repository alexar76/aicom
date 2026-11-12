# AIMarket Hub 3.19.0 — outside x402 sellers, ARD, and payment checks against the chain

```bash
pip install aimarket-hub==3.19.0
```

The last GitHub release was v3.2.1 (2026-08-12). PyPI has shipped every version since; 3.19.0 was published on 2026-11-08. What changed:

- **3.19.0:**
  - **Peer catalogues.** A crawl refuses a peer's catalogue that is older than the newest one it already verified from that peer under the same pinned key.
  - **Buyer pseudonym.** The operator's own providers receive `X-AIMarket-Buyer-Ref`, one stable pseudonym per authenticated buyer.
  - **No prices in MCP tool definitions.** Every price change used to change the definitions, so clients that pin them (WARDEN, ARGUS, mcp-scan) stopped using the hub until someone re-approved it.
  - **Federation limits.** Work started by unauthenticated federation announcements is bounded, and outbound federation requests check every DNS answer and pin the address they connect to.
- **3.18.0: Agent Resource Discovery (ARD).** Every hub serves `/.well-known/ard.json`, a `did:web` document and an ARD registry at `/ard/v1`. These follow the IETF DAWN drafts submitted on 2026-10-30.
- **3.17.1: payments.**
  - A channel refund obligation closes only against a payout the hub has checked on chain.
  - A seller-direct x402 payment and its invoice are recorded in one transaction.
  - A delivered call's work receipt is written onto its payment row.
- **Outside x402 sellers ("observed" tier, 2026-10-30).**
  - With the seller's consent, a hub lists routes from the seller's own `/.well-known/x402`, as long as they answer an unpaid request with a 402.
  - These routes are kept apart from the signed catalogue (`observed` in `/search`).
  - The hub's own 402s carry a signed x402 Offer, and settled calls a signed Receipt (EdDSA, `did:key`).
- **3.16.x (2026-10-20 to 10-29):**
  - A mandate can require its owner's approval above a threshold.
  - A2A tasks push their state to a webhook and survive a restart.
  - Owners get notifications in Telegram, Slack, Jira or a webhook.
  - Card top-ups go through Stripe Checkout, off by default.
  - The October security fixes, among them: a reverse proxy on the same host is no longer treated as "this machine".

Full history: [CHANGELOG.md](https://github.com/alexar76/aicom/blob/main/CHANGELOG.md) in the aicom monorepo, `aimarket-hub/`.
