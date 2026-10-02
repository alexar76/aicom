# ERC-8004 identities: AIMarket Hub, HISTOR and WARDEN

**English** · [Русский](erc-8004-identities.ru.md) · [Español](erc-8004-identities.es.md) · [Français](erc-8004-identities.fr.md) · [中文](erc-8004-identities.zh.md)

Since 2026-10-01 three of our services are registered agents in the
[ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) IdentityRegistry on Base mainnet. Any agent,
wallet or explorer that reads the registry finds each of them, who owns it, and a registration
file that says what the service is and where to reach it.

## The three agents

| Agent | agentId | What it is | Registration file | Explorer |
|---|---|---|---|---|
| AIMarket Hub | `96682` | Federated market of agent capabilities, sold per call over MCP, A2A and x402 | [aimarket-hub.json](https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json) | [8004scan](https://8004scan.io/agents/base/96682) |
| HISTOR | `96683` | Transparency log for MCP servers: what each server advertised, and when it changed | [histor.json](https://modelmarket.dev/.well-known/erc-8004/histor.json) | [8004scan](https://8004scan.io/agents/base/96683) |
| WARDEN | `96684` | MCP firewall: scans tool definitions before a host shows them to a model | [warden.json](https://modelmarket.dev/.well-known/erc-8004/warden.json) | [8004scan](https://8004scan.io/agents/base/96684) |

## On-chain record

- **Registry:** IdentityRegistry
  [`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432)
  on Base mainnet (chain id 8453), `AgentIdentity` version 2.0.0 — the canonical ERC-8004
  deployment, not a copy of our own.
- **Owner of all three:** the operator wallet
  [`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a).
- **Call:** one `register(string agentURI)` per agent; the agentURI is the registration file's URL.

| Agent | Transaction | Block |
|---|---|---|
| AIMarket Hub (`96682`) | [`0x207807…284bae`](https://basescan.org/tx/0x207807bbd9dc346e775f8db3cb2aa6b59190fe27e8b4b15d75eb9f5175284bae) | 52046664 |
| HISTOR (`96683`) | [`0xcec3de…f68fd6`](https://basescan.org/tx/0xcec3deb9a343b7257d4d83cbcb80cc3831647d0a907552a7ee14f7dcf7f68fd6) | 52046664 |
| WARDEN (`96684`) | [`0xa784ca…937fda`](https://basescan.org/tx/0xa784cacbea144ed5d9f9ac98e36ae3175f06907c3f8f7f308d5f5c7b37937fda) | 52046664 |

- **Cost:** 0.0000031 ETH in gas for all three.
- **Verified after mining:** `ownerOf` returns the operator wallet and `tokenURI` returns the
  registration file's URL, for each agentId.
- **Not done:** nothing is written to the ReputationRegistry, by choice, and the ValidationRegistry
  has no canonical deployment to write to. The reasoning: [ERC-8004 alignment](erc-8004-alignment.md).

## Registration files

Each agentURI resolves to an EIP-8004 `registration-v1` JSON document served from
`https://modelmarket.dev/.well-known/erc-8004/`: name, description, image, the service endpoints
(web page, MCP, A2A, A2MCP, x402, DID or npm package, depending on the agent) and a `registrations`
entry that names the agentId and the registry as `eip155:8453:0x8004A169…a432`.

`https://modelmarket.dev/.well-known/agent-registration.json` lists all three agentIds. It is the
domain proof for modelmarket.dev, which serves the registration files and the hub and A2MCP
endpoints: that domain confirms these registrations are its own. HISTOR's and WARDEN's own
web domains confirm theirs too: `https://histor.modelmarket.dev/.well-known/agent-registration.json`
lists `96683` and `https://warden.modelmarket.dev/.well-known/agent-registration.json` lists `96684`.

A file can change without a new transaction, because the agentURI on-chain points at the URL,
not at the content: edit `build.py`, regenerate, upload.

## The hub declares its identity

The apex hub states its agentId inside its own signed discovery document,
[`/.well-known/ai-market.json`](https://modelmarket.dev/.well-known/ai-market.json), in an
`erc8004` block:

```json
{
  "agent_id": "96682",
  "chain": "eip155:8453",
  "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
  "reputation_registry": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
  "agent_uri": "https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json",
  "verified_by_this_hub": false
}
```

`verified_by_this_hub: false` is deliberate. The claim is self-declared: a reader confirms it
against the registry rather than taking the hub's word. Any hub operator can do the same with
`AIMARKET_ERC8004_AGENT_ID`, `AIMARKET_ERC8004_CHAIN`, `AIMARKET_ERC8004_NETWORK` and
`AIMARKET_ERC8004_AGENT_URI` after registering from their own wallet.

## Check it yourself

Everything above can be checked without trusting us:

```bash
REG=0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
RPC=https://mainnet.base.org
cast call $REG "ownerOf(uint256)(address)" 96682 --rpc-url $RPC    # 0x1218ff36…Ad0a
cast call $REG "tokenURI(uint256)(string)" 96682 --rpc-url $RPC    # …/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/agent-registration.json
curl -s https://modelmarket.dev/.well-known/ai-market.json | jq .erc8004
```

For HISTOR or WARDEN, use `96683` or `96684` in the `cast` lines and `histor.json` or `warden.json`
in the first `curl`; the `erc8004` block exists only in the hub's document.

## Sources

- [`deploy/erc-8004/`](../deploy/erc-8004/): `build.py` writes the registration files,
  `register.py` registers them (a dry run unless given `--send`; it refuses when the wallet cannot
  cover the worst-case cost including Base's L1 data fee, skips any agent already in `ids.json`,
  and signs in-process so the key never reaches a command line), `ids.json`, `registrations.log`.
- The [on-chain journal](onchain-journal.md) entry of 2026-10-01.
- [ERC-8004 alignment](erc-8004-alignment.md): how this protocol's identities, receipts and
  reputation map onto ERC-8004, and what it deliberately leaves out.
