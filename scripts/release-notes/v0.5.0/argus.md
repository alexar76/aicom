# ARGUS 0.5.0 — WARDEN 0.29.0, a keystore fix, and eSIM prices that hold

Since 0.4.0 (2026-11-15):

- **WARDEN 0.29.0** (rulesets 21–23 and the `malware-list` gate). A refusal about something else no longer excuses a credential request after a colon, dash or comma, honest refusals still pass, and an MCP server started from an npm or PyPI package OpenSSF lists as malware is not started. Pins stored by 0.27.0 verify unchanged.
- **Keystore:** AES-GCM tags are fixed at 16 bytes, so a keystore or memory file with a cut-short tag fails to decrypt instead of lowering the forgery bound to 2^32. Files ARGUS wrote decrypt as before.
- **eSIM purchases:** `esim_buy` sends the quote's `quote_token`, so a seller on esim-kit 0.5 asks at most the quoted price while it is valid; a `409` with `current_offer` (nothing charged) is taken once within the cap.
- **Purchases can open their browser again:** `playwright-core` is back at 1.64.1, the version of the checkout browser kit. 0.4.0 shipped 1.65.0, and a 1.64 Playwright server refuses a 1.65 client ("version mismatch"), so `/buy_hudson` and the itch.io checkout could not start with the kit's browser.
- **Dependencies:** `pdfjs-dist` 6.5.438 (npm audit). Ecosystem knowledge says "Agent Capital Exchange".

```bash
npm install -g @alexar76/argus3@0.5.0
```

Full list: [CHANGELOG.md](CHANGELOG.md).
