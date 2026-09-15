# ERC-8004 alignment

How AIMarket relates to [ERC-8004 "Trustless Agents"](https://eips.ethereum.org/EIPS/eip-8004),
what is implemented, and what is deliberately not.

> Everything on-chain below was **verified by direct RPC reads against Ethereum mainnet and
> Base mainnet on 2026-08-28**, not taken from documentation. Where a fact could not be
> verified it is marked as such.

---

## 1. What ERC-8004 is, in one paragraph

Three per-chain singleton registries that give an agent a portable on-chain identity and a
public record of what others said about it. **IdentityRegistry** is an ERC-721 where
`tokenId` *is* the agentId and `tokenURI` *is* the agentURI. **ReputationRegistry** records
client feedback as a signed fixed-point integer with two free-form tags.
**ValidationRegistry** defines request/response hooks for validators (zkML, TEE,
re-execution).

It specifies **identity and reputation**. It does not specify payment — the EIP says so
explicitly and mentions x402 only as an example of a signal that could enrich feedback.

## 2. Canonical addresses (verified on-chain)

| Registry | Address | Verified |
|---|---|---|
| IdentityRegistry | `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` | ✅ Ethereum mainnet + Base mainnet |
| ReputationRegistry | `0x8004BAa17C55a88189AE136b182e5fdA19dE9b63` | ✅ Ethereum mainnet + Base mainnet |
| ValidationRegistry | **none published** | ✅ verified absent — see §5 |

Both are ERC-1967 minimal proxies (130 bytes) sharing the same implementation addresses on
both chains, and the canonical repository lists the same pair for roughly 25 mainnets.
`IdentityRegistry.name()` returns `"AgentIdentity"`, `symbol()` returns `"AGENT"`, and
`getVersion()` returns `"2.0.0"` on both registries on both chains.
`ReputationRegistry.getIdentityRegistry()` returns the Identity address, so the wiring is
confirmed rather than assumed.

Testnet pair (Sepolia, Base Sepolia, and others): identity
`0x8004A818BFB912233c491871b3d84c89A494BD9e`, reputation
`0x8004B663056A597Dffe9eCcC1965A193B7388713`.

> Both address families begin `0x8004`, matching the ERC number, which strongly suggests a
> mined CREATE2 salt. The canonical repository does not document CREATE2, a factory or a
> salt, so **treat cross-chain address identity as an observed fact and not a guarantee**.
> Verify the address on any chain before using it there.

## 3. How the two models line up

| ERC-8004 | AIMarket | Relationship |
|---|---|---|
| IdentityRegistry — agentId, agentURI | `.well-known/ai-market.json` at a hub URL | Complementary. An agentURI can point at the discovery document, giving an on-chain anchor to an off-chain identity |
| ReputationRegistry — client feedback on-chain | Signed reputation events, aggregated cross-hub (spec §5) | Overlapping. Ours is portable between hubs and verifiable without a chain; theirs is globally visible and censorship-resistant. Neither subsumes the other |
| ValidationRegistry — validator attestations | AWR receipts + Metis verification | Overlapping in intent, different in placement: AWR is an off-chain W3C Verifiable Credential; the registry is an on-chain anchor. They compose — the receipt is the evidence, the registry entry is the pointer |
| (not specified) | Payment: escrow channels, HTTP 402, x402 | ERC-8004 leaves payment out by design |
| (not specified) | Federated discovery across independent indexes | Also out of scope for ERC-8004 |

The honest summary: **ERC-8004 and AIMarket overlap on reputation and validation, and are
complementary everywhere else.** Neither replaces the other, and a hub can carry an ERC-8004
identity while running this protocol unchanged.

## 4. What is implemented here

A hub can **declare** an ERC-8004 identity it owns. Set:

```bash
AIMARKET_ERC8004_AGENT_ID=4242        # the tokenId from your Registered event
AIMARKET_ERC8004_CHAIN=base           # emitted as CAIP-2, e.g. eip155:8453
AIMARKET_ERC8004_NETWORK=mainnet      # mainnet | testnet — selects the registry pair
AIMARKET_ERC8004_AGENT_URI=…          # optional; defaults to this hub's .well-known
```

The declaration then appears in `/.well-known/ai-market.json` under `erc8004`, **inside the
document signature** so a relay cannot rewrite it in transit.

```json
"erc8004": {
  "agent_id": "4242",
  "chain": "eip155:8453",
  "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
  "reputation_registry": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
  "agent_uri": "https://your-hub.example/.well-known/ai-market.json",
  "verified_by_this_hub": false
}
```

`verified_by_this_hub` is `false` and always will be. The hub reports what its operator told
it. A reader who cares whether the claim is true reads the registry — which is the entire
point of the identity being on-chain, and why this hub does not pretend to have checked.

## 5. What is not implemented, and why

**Registering an identity.** `register(string agentURI)` is an on-chain transaction from the
operator's own wallet. A server does not send transactions on its owner's behalf, and no
amount of convenience justifies it. Register yourself, then set `AIMARKET_ERC8004_AGENT_ID`.

**Writing reputation on-chain.** Mirroring this protocol's reputation events into the
ReputationRegistry means a transaction per event, paid by someone, with a governance
question attached: whose judgement is being published, and can it be withdrawn? That is a
design decision, not an integration task.

**Anything touching ValidationRegistry.** It has **no published canonical deployment on any
chain** — the canonical repository lists Identity and Reputation addresses for ~25 mainnets
and none for Validation, and `eth_getCode` at the obvious vanity-pattern guess returns empty
on both Ethereum and Base mainnet. Its specification section is also flagged as under active
revision with the TEE community. Building on it today means self-deploying and accepting
future churn.

## 6. Open questions

- The EIP-712 typehash used by `setAgentWallet` is not in the EIP text. The domain was
  confirmed live (`name: "ERC8004IdentityRegistry"`, `version: "1"`, `verifyingContract` =
  the registry), but anyone implementing wallet re-binding must read
  `IdentityRegistryUpgradeable.sol` for the typehash.
- The EIP's Test Cases section is commented out, so there are no normative vectors to check
  an implementation against.
- `getVersion()` returns `"2.0.0"` on the live contracts, while third-party material refers
  to a "Jan 2026 spec (v1.2)". These two numbering schemes could not be reconciled against
  the EIP, which carries no version field of its own.

## 7. Related

- [`aimarket-hub/aimarket_hub/x402.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/x402.py) — the declaration builder and the registry addresses
- [`join-the-federation.md`](join-the-federation.md) — x402 and Bazaar interoperability
- [`awr-receipts.md`](awr-receipts.md) — the receipt format that would anchor into a validation registry
