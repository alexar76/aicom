#!/usr/bin/env python3
"""Generate README doc index + docs/ package for every AIMarket Hub plugin."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PLUGINS: dict[str, dict] = {
    "plugins/aimarket-safety": {
        "title": "aimarket-safety",
        "category": "security",
        "tagline": "Pre/post-invoke safety classifier with constitutional contracts",
        "install": "pip install aimarket-safety",
        "endpoints": [
            ("GET", "/ai-market/v2/p/aimarket-safety/safety/constitutional", "List constitutional contracts"),
        ],
        "hooks": ["on_invoke_pre_check", "on_invoke_post_check"],
        "integration_snippet": '''curl http://localhost:9080/ai-market/v2/invoke \\
  -H "Content-Type: application/json" \\
  -d '{"product_id":"prod-demo","capability_id":"translate@v1","input":{"text":"hello"}}'
# Blocked requests return signed rejection receipt + automatic channel refund''',
        "user_cases": [
            ("Marketplace operator", "Protect all providers from jailbreak/injection without per-capability code"),
            ("Enterprise buyer", "Require constitutional contract: no PII, no medical data in transit"),
            ("Auditor", "Collect signed rejection receipts proving unsafe calls were blocked, not billed"),
        ],
    },
    "plugins/aimarket-reputation": {
        "title": "aimarket-reputation",
        "category": "reputation",
        "tagline": "Stake-bond + signed outcomes + dispute resolution",
        "install": "pip install aimarket-reputation",
        "endpoints": [
            ("GET", "/ai-market/v2/reputation/{hub_url}", "Trust score breakdown"),
            ("POST", "/ai-market/v2/reputation/events", "Submit signed reputation events"),
        ],
        "hooks": ["on_invoke_post_check"],
        "integration_snippet": '''curl "https://modelmarket.dev/ai-market/v2/reputation/https://provider.example.com"''',
        "user_cases": [
            ("Consumer", "Compare trust scores before opening a payment channel"),
            ("Provider", "Stake USDT bond to rank higher in federated search"),
            ("Dispute auditor", "Slash bond when signed consumer dispute is upheld"),
        ],
    },
    "plugins/aimarket-channels": {
        "title": "aimarket-channels",
        "category": "infrastructure",
        "tagline": "Pre-funded payment channels — off-chain ledger, on-chain settlement",
        "install": "pip install aimarket-channels",
        "endpoints": [
            ("POST", "/ai-market/v2/channel/open", "Open pre-funded channel"),
            ("POST", "/ai-market/v2/channel/close", "Settle and refund remainder"),
        ],
        "hooks": [],
        "integration_snippet": '''ch = requests.post(f"{HUB}/ai-market/v2/channel/open", json={"deposit_usd": 5.0}).json()
headers = {"X-Payment-Channel": ch["channel"]["channel_id"]}
requests.post(f"{HUB}/ai-market/v2/invoke", json={...}, headers=headers)''',
        "user_cases": [
            ("Agent orchestrator", "One deposit, N micro-invokes, one settlement TX"),
            ("Mobile app", "Pre-fund $5 wallet for session; refund unused balance on exit"),
            ("Batch ETL", "Run 50 capability calls without 50 on-chain transactions"),
        ],
    },
    "plugins/aimarket-tee": {
        "title": "aimarket-tee",
        "category": "security",
        "tagline": "TEE-attested execution (AWS Nitro / Intel TDX)",
        "install": "pip install aimarket-tee",
        "endpoints": [],
        "hooks": ["on_invoke_post_check"],
        "integration_snippet": '''from aimarket_tee.tee_attestation import TEEAttestationService
result = TEEAttestationService().execute_with_attestation(
    capability_id="legal.review@v1", input_payload={"documents": {...}}
)
print(result["attestation"]["platform"], result["receipt"]["input_hash"])''',
        "user_cases": [
            ("Legal tech", "Prove NDA text never left the enclave in plaintext"),
            ("Healthcare", "HIPAA-friendly invoke with hardware attestation report"),
            ("Model vendor", "Deploy weights inside Nitro; hub operator cannot extract"),
        ],
    },
    "plugins/aimarket-auction": {
        "title": "aimarket-auction",
        "category": "monetization",
        "tagline": "Real-time spot bidding for capability slots",
        "install": "pip install aimarket-auction",
        "endpoints": [
            ("POST", "/ai-market/v2/p/aimarket-auction/auction/bid", "Place bid on capability slot"),
            ("GET", "/ai-market/v2/p/aimarket-auction/auction/{capability_id}", "Current auction state"),
        ],
        "hooks": [],
        "integration_snippet": '''requests.post(f"{HUB}/ai-market/v2/p/aimarket-auction/auction/bid", json={
  "capability_id": "translate.multi@v2", "bid_usd": 0.35, "wallet": "0x..."
})''',
        "user_cases": [
            ("Provider", "Sell scarce GPU windows to highest bidder each hour"),
            ("Consumer", "Get cheaper off-peak translation when demand is low"),
            ("Market maker", "Arbitrage price gaps between peer hubs"),
        ],
    },
    "plugins/aimarket-personas": {
        "title": "aimarket-personas",
        "category": "tooling",
        "tagline": "Auto-generated AI agent personas for chat-native discovery",
        "install": "pip install aimarket-personas",
        "endpoints": [
            ("GET", "/ai-market/v2/p/aimarket-personas/personas", "List generated personas"),
            ("POST", "/ai-market/v2/p/aimarket-personas/personas/generate", "Generate persona for niche"),
        ],
        "hooks": [],
        "integration_snippet": '''requests.post(f"{HUB}/ai-market/v2/p/aimarket-personas/personas/generate", json={
  "niche": "fintech compliance", "platform": "claude"
})''',
        "user_cases": [
            ("Hub marketing", "Persona cards in discovery UI for non-technical buyers"),
            ("MCP author", "Auto persona + tool list for packaged capability"),
            ("Sales", "Demo agent that speaks buyer language per vertical"),
        ],
    },
    "plugins/aimarket-streaming": {
        "title": "aimarket-streaming",
        "category": "monetization",
        "tagline": "SSE/WS streaming with per-chunk micro-billing",
        "install": "pip install aimarket-streaming",
        "endpoints": [
            ("GET", "/ai-market/v2/p/aimarket-streaming/stream/{capability_id}", "SSE token stream"),
        ],
        "hooks": ["on_invoke_post_check"],
        "integration_snippet": '''# Open channel first, then stream with X-Payment-Channel header
with requests.get(f"{HUB}/ai-market/v2/p/aimarket-streaming/stream/llm.chat@v1",
                  headers={"X-Payment-Channel": ch_id}, stream=True) as r:
    for line in r.iter_lines(): ...''',
        "user_cases": [
            ("Chat UI", "Bill per token chunk instead of flat per-response fee"),
            ("Long reports", "Stop stream early; pay only for generated tokens"),
            ("Live coding agent", "Micro-receipt after each SSE event for audit trail"),
        ],
    },
    "plugins/aimarket-nft": {
        "title": "aimarket-nft",
        "category": "monetization",
        "tagline": "Tokenized pre-paid credits (ERC-721)",
        "install": "pip install aimarket-nft",
        "endpoints": [
            ("POST", "/ai-market/v2/p/aimarket-nft/mint", "Mint credit NFT"),
            ("POST", "/ai-market/v2/p/aimarket-nft/redeem", "Redeem NFT balance to channel"),
        ],
        "hooks": [],
        "integration_snippet": '''requests.post(f"{HUB}/ai-market/v2/p/aimarket-nft/redeem", json={
  "token_id": "42", "contract": "0xCredits...", "wallet": "0x..."
})''',
        "user_cases": [
            ("Gift cards", "Sell transferable AI credit bundles as NFTs"),
            ("Secondary market", "Resell unused prepaid balance"),
            ("Loyalty program", "Mint monthly credit drops to holder wallets"),
        ],
    },
    "plugins/aimarket-mcp-packager": {
        "title": "aimarket-mcp-packager",
        "category": "tooling",
        "tagline": "Package capabilities as MCP servers for Claude Desktop",
        "install": "pip install aimarket-mcp-packager",
        "endpoints": [
            ("POST", "/ai-market/v2/p/aimarket-mcp-packager/package", "Build MCP manifest + Docker"),
            ("GET", "/ai-market/v2/p/aimarket-mcp-packager/package/{id}", "Download package status"),
        ],
        "hooks": [],
        "integration_snippet": '''requests.post(f"{HUB}/ai-market/v2/p/aimarket-mcp-packager/package", json={
  "capability_id": "translate.multi@v2", "product_id": "prod-translate"
})''',
        "user_cases": [
            ("Capability author", "One-click MCP + Claude Desktop config from hub listing"),
            ("Enterprise IT", "Self-host MCP server with hub billing still attached"),
            ("Anthropic registry path", "Generate spec-compliant MCP bundle for submission"),
        ],
    },
    "plugins/aimarket-orchestrator": {
        "title": "aimarket-orchestrator",
        "category": "monetization",
        "tagline": "NL task planner — decomposes tasks into capability chains (1% fee)",
        "install": "pip install aimarket-orchestrator",
        "endpoints": [
            ("POST", "/ai-market/v2/p/aimarket-orchestrator/orchestrator/plan", "Plan multi-step task"),
        ],
        "hooks": [],
        "integration_snippet": '''plan = requests.post(f"{HUB}/ai-market/v2/p/aimarket-orchestrator/orchestrator/plan", json={
  "task": "Translate contract to French then summarize risks", "budget_usd": 5.0
}).json()''',
        "user_cases": [
            ("No-code user", "Describe outcome; hub picks capability chain"),
            ("Autonomous agent", "Planner returns DAG + cost estimate before spend"),
            ("Workflow SaaS", "Embed orchestrator as paid meta-capability"),
        ],
    },
    "plugins/aimarket-data-cap": {
        "title": "aimarket-data-cap",
        "category": "monetization",
        "tagline": "Private RAG corpus exposed as paid search capability",
        "install": "pip install aimarket-data-cap",
        "endpoints": [
            ("POST", "/ai-market/v2/p/aimarket-data-cap/index", "Register private corpus"),
            ("POST", "/ai-market/v2/p/aimarket-data-cap/search", "Paid semantic search"),
        ],
        "hooks": [],
        "integration_snippet": '''requests.post(f"{HUB}/ai-market/v2/p/aimarket-data-cap/search", json={
  "corpus_id": "legal-precedents-us", "query": "arbitration clause enforceability CA"
})''',
        "user_cases": [
            ("Law firm", "Monetize internal precedent library without exporting raw docs"),
            ("Research lab", "Sell anonymized embedding search, not dataset download"),
            ("Enterprise KB", "Charge per query against private Confluence export"),
        ],
    },
    "plugins/aimarket-promo": {
        "title": "aimarket-promo",
        "category": "monetization",
        "tagline": "Signed time-locked discount offers (yield management)",
        "install": "pip install aimarket-promo",
        "endpoints": [
            ("POST", "/ai-market/v2/p/aimarket-promo/offer/create", "Create signed discount"),
            ("POST", "/ai-market/v2/p/aimarket-promo/offer/redeem", "Redeem at invoke time"),
        ],
        "hooks": ["on_invoke_pre_check"],
        "integration_snippet": '''offer = requests.post(f"{HUB}/ai-market/v2/p/aimarket-promo/offer/create", json={
  "capability_id": "translate@v1", "discount_pct": 20, "expires_at": "2026-06-01T00:00:00Z"
}).json()''',
        "user_cases": [
            ("Provider", "Fill idle GPU windows with 30% off flash sales"),
            ("Affiliate", "Signed promo codes tracked in settlement receipt"),
            ("Seasonal campaign", "Auto-expire offers; no manual coupon DB"),
        ],
    },
    "plugins/aimarket-dataset": {
        "title": "aimarket-dataset",
        "category": "tooling",
        "tagline": "Weekly anonymized invocation corpus (CC-BY 4.0)",
        "install": "pip install aimarket-dataset",
        "endpoints": [
            ("GET", "/ai-market/v2/p/aimarket-dataset/export/latest", "Latest anonymized corpus"),
            ("GET", "/ai-market/v2/p/aimarket-dataset/export/{week}", "Corpus for ISO week"),
        ],
        "hooks": [],
        "integration_snippet": '''corpus = requests.get(f"{HUB}/ai-market/v2/p/aimarket-dataset/export/latest").json()
# intent patterns, category demand — no PII, no raw payloads''',
        "user_cases": [
            ("Researcher", "Train demand forecasting on real marketplace telemetry"),
            ("Builder", "See which intents lack supply before building capability"),
            ("Open data fund", "Publish CC-BY corpus for ecosystem transparency"),
        ],
    },
    "plugins/aimarket-zk": {
        "title": "aimarket-zk",
        "category": "security",
        "tagline": "ZK proofs for private AI invocation",
        "install": "pip install aimarket-zk",
        "endpoints": [
            ("POST", "/ai-market/v2/p/aimarket-zk/prove/input", "Prove valid input without revealing"),
            ("POST", "/ai-market/v2/p/aimarket-zk/prove/output", "Prove correct execution"),
            ("POST", "/ai-market/v2/p/aimarket-zk/verify", "Verify proof bundle"),
        ],
        "hooks": ["on_invoke_pre_check", "on_invoke_post_check"],
        "integration_snippet": '''from aimarket_zk.zk_proofs import ZKProver
proof = ZKProver(signer).prove_input("legal.review@v1", schema, secret_input)''',
        "user_cases": [
            ("M&A team", "Prove contract was reviewed without revealing deal terms"),
            ("Model IP owner", "Prove inference ran correctly without exposing weights"),
            ("Regulator", "Verify compliance event occurred without document disclosure"),
        ],
    },
    "aimarket-hub/plugins/aimarket-provenance": {
        "title": "aimarket-provenance",
        "category": "compliance",
        "tagline": "Cryptographic provenance receipts for every AI output (Ed25519 + W3C VC)",
        "install": "pip install -e aimarket-hub/plugins/aimarket-provenance",
        "plugin_name": "provenance",
        "endpoints": [
            ("POST", "/ai-market/v2/p/provenance/attest", "Create provenance receipt (Bearer auth optional)"),
            ("GET", "/ai-market/v2/p/provenance/receipt/{id}", "Fetch stored receipt"),
            ("GET", "/ai-market/v2/p/provenance/verify/{id}", "Verify signature + chain"),
        ],
        "hooks": ["on_invoke_post_check"],
        "integration_snippet": '''# Auto-attached on every invoke response:
r = requests.post(f"{HUB}/ai-market/v2/invoke", json={...}).json()
print(r.get("provenance_receipt"))  # {"receipt_id": "...", "verify_url": "..."}

# Manual attest:
requests.post(f"{HUB}/ai-market/v2/p/provenance/attest",
  headers={"Authorization": "Bearer $AIMARKET_PROVENANCE_API_TOKEN"},
  json={"model_id": "translate@v1", "input": {...}, "output": {...}})''',
        "user_cases": [
            ("Compliance officer", "Archive W3C VC receipt per regulated AI decision"),
            ("Consumer app", "Show verify.aimarket.org link next to every AI answer"),
            ("Multi-step pipeline", "Chain parent_receipts for auditable DAG of model calls"),
        ],
    },
}


def user_guide(meta: dict) -> str:
    title = meta["title"]
    plugin_name = meta.get("plugin_name", title)
    eps = meta.get("endpoints", [])
    ep_table = "\n".join(f"| `{m}` | `{p}` | {d} |" for m, p, d in eps) if eps else "| — | — | Hooks only (no public routes) |"
    hooks = ", ".join(f"`{h}`" for h in meta.get("hooks", [])) or "none"
    return f"""# {title} — User Guide

## What it does

{meta['tagline']}. Category: **{meta['category']}**.

## Installation

```bash
{meta['install']}
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="{plugin_name}")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{{plugin_name}}/`.

Invoke hooks: {hooks}

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
{ep_table}

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.{plugin_name.replace("aimarket-", "")}'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
"""


def sdk_integration(meta: dict) -> str:
    return f"""# {meta['title']} — SDK Integration

## Quick integration

```python
import requests

HUB = "http://localhost:9080"  # or https://modelmarket.dev

# 1. Confirm plugin is loaded
plugins = requests.get(f"{{HUB}}/ai-market/v2/plugins").json()
assert any(p["name"] == "{meta['title']}" for p in plugins["plugins"])

# 2. Example call
{meta['integration_snippet']}
```

## Invoke hook behavior

When this plugin registers invoke hooks, the hub calls them automatically on every `/ai-market/v2/invoke`:

1. **Pre-check** — can block input (safety, ZK input proof, promo validation)
2. **Post-check** — can block output or attach metadata (provenance receipt, TEE attestation)

Blocked invocations return HTTP 403 with signed rejection receipt and channel refund when applicable.

## Manifest extension

After install, the hub merges plugin fields into `/.well-known/ai-market.json` under `plugin_extensions`.

## Python package import

```python
# Direct library use (without HTTP)
import {meta['title'].replace("-", "_")}  # adjust to package name
```

## Related plugins

See [AIMarket Hub README](../../../aimarket-hub/README.md#14-plugins) for the full plugin catalog.
"""


def user_cases(meta: dict) -> str:
    rows = "\n".join(
        f"### {persona}\n\n{story}\n" for persona, story in meta["user_cases"]
    )
    return f"""# {meta['title']} — User Cases

{rows}

## Cross-plugin workflows

| Combine with | Workflow |
|--------------|----------|
| `aimarket-channels` | Pre-fund session, run plugin features, settle once |
| `aimarket-safety` | Block unsafe calls before paid invoke |
| `aimarket-provenance` | Attach receipt to every successful invoke |
| `aimarket-reputation` | Weight search results by provider trust score |
"""


def doc_index_block(title: str) -> str:
    return f"""
## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---
"""


def ensure_readme(root: Path, meta: dict) -> None:
    readme = root / "README.md"
    if not readme.is_file():
        # Full README for plugins without one (provenance)
        readme.write_text(
            f"# {meta['title']}\n\n**{meta['tagline']}**\n"
            + doc_index_block(meta["title"])
            + f"\n## Installation\n\n```bash\n{meta['install']}\n```\n",
            encoding="utf-8",
        )
        return
    text = readme.read_text(encoding="utf-8")
    if "## Documentation" not in text:
        lines = text.split("\n", 1)
        if len(lines) == 2 and lines[0].startswith("#"):
            text = lines[0] + "\n" + doc_index_block(meta["title"]) + lines[1]
        else:
            text = doc_index_block(meta["title"]) + text
        readme.write_text(text, encoding="utf-8")


def main() -> None:
    for rel, meta in PLUGINS.items():
        root = ROOT / rel
        docs = root / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "user-guide.md").write_text(user_guide(meta), encoding="utf-8")
        (docs / "sdk-integration.md").write_text(sdk_integration(meta), encoding="utf-8")
        (docs / "user-cases.md").write_text(user_cases(meta), encoding="utf-8")
        ensure_readme(root, meta)
        print(f"OK {rel}")

    # Plain-language value blocks (EN + RU) — must run after user-guide is written
    import subprocess
    subprocess.run(
        ["python3", str(ROOT / "scripts" / "bootstrap_product_value.py")],
        check=False,
        cwd=ROOT,
    )


if __name__ == "__main__":
    main()
