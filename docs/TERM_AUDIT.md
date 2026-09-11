# Documentation and terminology audit

Audit target: the new Attested Memory SaaS documentation in `docs/i18n/`, the
public `/docs` index and the SaaS deployment runbooks.

## Completeness result

| Area | Result | Notes |
|---|---|---|
| Ten locales | Pass | `en`, `ru`, `es`, `pt-BR`, `de`, `fr`, `ja`, `ko`, `zh-CN`, `tr`. |
| Overview | Pass | Every locale explains the three products and first five minutes. |
| User guide | Pass with glossary support | Payment, key lifecycle, actor headers, team flow and errors are defined in the shared glossary. |
| Trial flow | Added | Actor-bound trial keys expire automatically; paid upgrade continues through the exact KOVA invoice flow. |
| Use cases | Pass | Personal memory, team memory, expert market and agent handoff are covered. |
| Screenshots | Pass as UI previews | Each locale has a language-specific `screenshots/dashboard.svg`; these are deterministic UI previews, not claims of a live payment state. |
| API reference | Partial | FastAPI/OpenAPI remains the exact contract; user docs explain route families but do not duplicate every schema. |
| Operator runbook | Pass | PostgreSQL, deployment, payment and security runbooks remain in the repository. |
| Legal/support docs | Gap | Terms, privacy, refunds, support SLA and jurisdiction-specific crypto disclosures still need legal/product-owner input. |

## User clarity review

The onboarding is understandable after the first page, but the following rules
are enforced in the glossary because they are common failure points:

- Explain “actor identity” before showing `X-Actor-ID` headers.
- Explain that a public wallet address is safe to share but a private key is not.
- Explain the difference between an invoice, a tx hash and confirmations.
- Explain that `402` is an expected paid-memory response, not a server crash.
- Explain that `403` can mean a valid key with the wrong product or team scope.
- Explain that `409` protects against double issuance and duplicate payment flows.
- Explain that `team_id` is an authorization boundary only when the gateway
  assertion and Hub actor signature both pass.

## Term comparison method

The glossary at [`docs/i18n/GLOSSARY.md`](i18n/GLOSSARY.md) is the editorial
source of truth. Before changing a localized guide:

1. Search the guide for a glossary term.
2. Check that its first use has a plain-language explanation.
3. Check that code identifiers remain unchanged.
4. Check that the translation preserves the security implication.
5. Run the locale completeness check and review the corresponding UI preview.

## External terminology references

Definitions were checked against [Ethereum EVM documentation](https://ethereum.org/developers/docs/evm/),
[RFC 8032 for Ed25519](https://www.rfc-editor.org/rfc/rfc8032),
[RFC 2104 for HMAC](https://www.rfc-editor.org/rfc/rfc2104/),
[RFC 8259 for JSON](https://www.rfc-editor.org/rfc/rfc8259),
[the MCP specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/index),
[PostgreSQL 16 documentation](https://www.postgresql.org/docs/16/),
[Base’s RPC documentation](https://docs.base.org/base-chain/api-reference/rpc-overview),
and [Circle’s USDC contract addresses](https://developers.circle.com/stablecoins/usdc-contract-addresses).
