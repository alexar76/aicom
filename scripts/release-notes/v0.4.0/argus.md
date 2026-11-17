# ARGUS 0.4.0 — WARDEN 0.27.0, mail, and purchases the owner turns on

Since 0.3.6 (2026-11-10):

- **WARDEN 0.27.0** (ruleset 20). An EVM opcode "mnemonic" is no longer read as a seed-phrase request (alexar76/warden#14), a request for the user's mnemonic still blocks, and each finding names the clause it fired on. Pins stored by WARDEN 0.24.0 verify under 0.27.0; a changed description still gives `TOOL_DEF_DRIFT`.
- **Mail.** `argus mail setup` on the host and `/mail` in the private owner chat. Reading, verification codes and replies are separate permissions; Outlook.com is incoming only.
- **Purchases from Telegram, off until the operator turns them on:** a Hudson Link single-ride ticket (`/buy_hudson`) and an itch.io checkout, paid with a Laso prepaid card through a separate checkout browser. Live mode plus `ARGUS_HUDSON_PURCHASE_ENABLED=1` or `ARGUS_ITCH_PURCHASE_ENABLED=1`; the owner confirms the total; the attempt is journalled before the order goes out, so a recheck reads the saved order instead of buying again.
- **Owner-approved paid lookups:** a CoinMarketCap quote over x402, paid search, browser access, market data.
- **Dependencies:** new `imapflow`, `mailparser`, `nodemailer`, `pdfjs-dist`, `playwright-core` (no browser download); `@x402/*` 2.30.0. The `@aimarket/agent` peer range is now ^0.4.0.

```bash
npm install -g @alexar76/argus3@0.4.0
```

Full list: [CHANGELOG.md](CHANGELOG.md).
