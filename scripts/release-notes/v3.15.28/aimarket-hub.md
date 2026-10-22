# aimarket-hub 3.15.28 — what changed since the 3.2.1 release (August)

The GitHub release page stopped at 3.2.1 while PyPI moved on. This note covers 3.15.x as a whole; `modelmarket.dev` runs 3.15.28.

- **One key pays where the free trial stops.** `/start` hands out an API key; the same key works on the MCP connection, the invoke API and, for clients that take a URL but no header, `https://modelmarket.dev/mcp/k/<key>` (the key is then part of the URL — prefer the header). A new key opens with the hub's signup credit.
- **USDC top-ups credit themselves.** USDC landing in the top-up wallet is credited without anyone presenting the transaction, and no single transfer can hold up the deposit watcher.
- **Post-quantum signatures by default.** A new hub signs hybrid (Ed25519 + ML-DSA); a hub that already holds an ML-DSA key keeps it across redeploys; every hub reads post-quantum signatures and says so when it cannot.
- **Joining the federation is one command.** `aimarket node` turns a service someone already runs into a federation node; a hub built from the quickstart is one other hubs admit; a hub's signed manifest names its own sellers' `provider_pubkey` (never a peer's).
- **Payments hold up under review.** A payment channel spends only with its secret; an escrow window is collected whole and short deadlines are refused; a channel debit that moves money must name its receipt; a hub that relays a direct x402 sale no longer asks for its own fee first.
- **Pay-on-Verified.** A buyer can hold payment until an independent verdict; the verdict's limits are documented in five languages.
- **Reputation from buyers.** Buyer-confirmed deliveries let a seller paid directly show that it delivers; a listing whose answer does not depend on its input ranks after the ones whose answer does.
- **Readable code.** `create_app()` was one 8,400-line closure and `/invoke` one 2,429-line function; both now read in parts (`aimarket_hub/hub_routes/`), moved without behaviour changes.

```bash
pip install aimarket-hub==3.15.28
```
