# Attested Memory technical glossary

This glossary is the terminology source of truth for the ten localized guides.
The first sentence is intentionally written for a non-technical user; the
second sentence is the precise implementation meaning. Product terms are
marked as **Attested Memory term** and must not be confused with standards.

## Identity, access and security

| Term | Plain-language meaning | Technical meaning / product rule |
|---|---|---|
| API | A way for another program to use the product. | HTTP endpoints that accept JSON requests and return JSON responses. |
| API key | A secret pass that identifies a paid SaaS entitlement. | An `ask_...` bearer credential; only a hash and prefix are stored, and the raw key is shown once. |
| Actor identity | The signed identity of a person, agent or service making a memory request. | `X-Actor-ID` is bound to `X-Actor-Public-Key`; `X-Actor-Signature` signs the actor ID and is verified by Memory Market. |
| Public key | The part of a key pair that can be shared. | The Ed25519 verification key sent in `X-Actor-Public-Key`. |
| Private key | The secret part that must never leave the client. | The Ed25519 signing key held by a browser wallet, agent runtime or secret manager. |
| Ed25519 | A modern public-key signature algorithm. | The EdDSA algorithm specified by [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032). |
| HMAC | A short proof that a trusted service created a message. | The gateway signs a five-minute team assertion with a shared secret; the Hub verifies it using constant-time comparison. HMAC is specified by [RFC 2104](https://www.rfc-editor.org/rfc/rfc2104/). |
| PQC | Cryptography designed to remain useful against future quantum-capable attacks. | Post-quantum controls in the Hub profile; it does not replace the current Ed25519 actor proof. |
| Scope | The boundary of what a credential may access. | Product scope (`personal`, `team`, `expert-market`) and, for teams, the `team:<id>` namespace. |
| Rate limit | A temporary cap on how many requests may be made. | Gateway request protection backed by PostgreSQL; a rejected request returns HTTP `429`. |

## Memory and trust

| Term | Plain-language meaning | Technical meaning / product rule |
|---|---|---|
| Memory Unit | One saved piece of knowledge. | The Hub object with title, content, tags, visibility, sources, truth state and provenance state. |
| Truth Layer | The part that records how well a claim is supported. | The service that stores evidence and a truth status such as `unverified`, `supported`, `contested` or `rejected`. |
| Provenance | The history showing where a memory came from and what happened to it. | A ledger receipt and lineage root attached to a Memory Unit when attestation succeeds. |
| Attestation | A signed statement from a trusted service about an event. | A Truth/Provenance receipt for events such as memory creation or paid sharing. |
| Namespace | A named container that separates one group’s data from another’s. | Team Memory records use a `team:<id>` tag and a verified team assertion; the Hub filters reads to that namespace. |
| Visibility | The read policy selected for a memory. | Hub values include `private`, `shared`, `public` and `paid`. |
| Source reference | A pointer to material that supports a memory. | A user-provided URI or reference stored in `source_refs`; it is not automatically proof of truth. |

## Payments and blockchain

| Term | Plain-language meaning | Technical meaning / product rule |
|---|---|---|
| EVM | The environment used by Ethereum-compatible smart contracts. | The Ethereum Virtual Machine executes smart-contract code consistently across nodes; see [Ethereum’s EVM documentation](https://ethereum.org/developers/docs/evm/). |
| Base | The Ethereum Layer 2 network used for checkout. | Base Mainnet uses chain ID `8453`; Base documents the mainnet and testnet IDs in its [RPC overview](https://docs.base.org/base-chain/api-reference/rpc-overview). |
| USDC | A dollar-denominated stablecoin. | The checkout accepts canonical Circle USDC on Base at `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`; verify addresses against [Circle’s contract list](https://developers.circle.com/stablecoins/usdc-contract-addresses). |
| Canonical token | The official token contract for a network. | For this product, only Circle USDC on Base is accepted; bridged or look-alike tokens are not interchangeable. |
| Invoice | A payment instruction created before money is sent. | KOVA returns the exact amount, recipient, token, chain, expiry and required confirmations. |
| Transaction / tx hash | The receipt identifier for a blockchain action. | A 32-byte transaction hash used by KOVA to locate and verify the payment; a hash alone is never proof of settlement. |
| Confirmation | A block inclusion count used to reduce reorg risk. | The payment is confirmed only when KOVA reports the invoice as `confirmed` with the required count. |
| Entitlement | The right to use a paid product or plan. | A gateway record linked to a confirmed invoice and represented by a time-bound SaaS key. |
| Trial | A short free period to test a product before paying. | An actor-bound, one-time entitlement issued by the Gateway without a KOVA invoice; it expires automatically and uses the same key lifecycle as paid access. |
| Non-custodial | The service does not hold the user’s wallet secret. | The gateway accepts a public payer address and transaction hash, but never a seed phrase or private key. |
| KOVA | The payment verification adapter. | The independent service that creates and re-checks generic Base USDC invoices; it is not the SaaS wallet. |

## Data and integration

| Term | Plain-language meaning | Technical meaning / product rule |
|---|---|---|
| JSON | A text format for structured data. | The API payload format defined by [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259). Never parse untrusted JSON with `eval`. |
| PostgreSQL | The production database. | PostgreSQL 16 stores Hub knowledge and SaaS orders, keys, memberships and rate-limit state. See the [PostgreSQL documentation](https://www.postgresql.org/docs/16/). |
| MCP | A standard way for AI applications to connect to tools and context. | Model Context Protocol uses JSON-RPC messages and supports stdio and Streamable HTTP transports; see the [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/index). |
| RPC | A network endpoint used to ask a blockchain node for data. | JSON-RPC endpoints used to inspect Base blocks and transactions; RPC availability does not itself confirm payment. |
| Idempotency key | A retry label that prevents duplicate work. | `Idempotency-Key` is required on SaaS order creation and is forwarded to KOVA so a browser retry does not create a second invoice. |

## Error codes in plain language

| Code | Meaning | User action |
|---|---|---|
| `401` | Identity or credential was not accepted. | Check `X-SaaS-Key` and all actor headers; never paste a private key. |
| `402` | The requested paid memory needs settlement. | Follow the returned invoice; do not send a random amount. |
| `403` | The credential is valid but not allowed for this product/team/memory. | Check the product plan, team membership and `team_id`. |
| `404` | The resource is not available to this request. | Check the ID and checkout token; the gateway intentionally hides other users’ orders. |
| `409` | The operation conflicts with an already finalized state. | Reuse the original checkout flow or rotate the active key; do not create a second payment. |
| `429` | Too many requests in the current window. | Wait for `Retry-After` and retry with the same idempotency key where applicable. |
| `503` | A dependent service is temporarily unavailable. | Retry later; operators should inspect KOVA, PostgreSQL and Hub health. |

### Editorial rules

1. Define a technical term before using it in a user action.
2. Keep endpoint names, JSON fields, headers, algorithms and env variables exact.
3. Never translate a security warning into softer marketing language.
4. Use “verification” for a technical check and “truth” only for the product’s
   evidence status; the system does not claim philosophical certainty.
