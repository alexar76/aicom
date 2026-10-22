# EMPORION 0.4.0 — public-record facts for agents that trade, every source licensed for resale

- **UN sanctions through licensed lists.** UN Security Council designations now come through the UK Sanctions List (Open Government Licence v3.0) and the EU list. The UN's own file carries no reuse licence and is no longer read. `sanctions.screen` covers OFAC-SDN, EU and UK; a hit carries `un_ref` when its list names one. Measured 2026-10-17: the three lists hold all 1,010 UN entries.
- **Bitcoin timestamps verified without block explorers** (0.3.0). EMPORION keeps its own header chain from genesis, fetched peer to peer and checked header by header; two nodes on different networks must agree before a header is used.
- **Registry terms respected** (0.3.0). RDAP is limited to 30 queries a minute per registry and cached for 24 hours, and the registry's own terms are passed through.
- **More company registers** (0.2.1): Finland (PRH, CC BY 4.0) and the United Kingdom (Companies House, OGL v3.0).
- 160 tests.

Full list: [CHANGELOG.md](https://github.com/alexar76/emporion/blob/main/CHANGELOG.md). Free MCP endpoint (no key, rate-limited): `https://modelmarket.dev/tools/mcp/emporion`. Registry name `dev.modelmarket/emporion`.
