# Domain Operator Kit 0.1.0 — pre-live

Sell domains to AI agents with your own registrar account and a fixed markup.

- A seller node quotes `.com`, `.net` and `.org` at supplier cost plus your fixed markup. The quote is signed and shows all three numbers before payment, which is x402 (USDC on Base).
- Registration to the real owner, owner-signed DNS changes, renewal at a new quote, and recovery when a response is lost.
- Suppliers: Openprovider and Porkbun out of the box, or any registrar behind the [HTTP supplier contract](https://github.com/alexar76/domain-operator-kit/blob/main/SUPPLIERS.md).
- Agents use the signed `domains.*@v1` capabilities, the JavaScript client or the stdio MCP configuration.

**Status: pre-live.** 57 local tests pass, and the Openprovider and Porkbun Sandbox pilots pass end to end. Production purchases, payment settlement and Vercel attachment are not live yet. See [PILOT.md](https://github.com/alexar76/domain-operator-kit/blob/main/PILOT.md).

Free availability and price quote for agents (no key): MCP `https://modelmarket.dev/tools/mcp/domains`, registry name `dev.modelmarket/domains`.
