# aimarket-nft — SDK Integration

## Quick integration

```python
import requests

HUB = "http://localhost:9080"  # or https://modelmarket.dev

# 1. Confirm plugin is loaded
plugins = requests.get(f"{HUB}/ai-market/v2/plugins").json()
assert any(p["name"] == "aimarket-nft" for p in plugins["plugins"])

# 2. Example call
requests.post(f"{HUB}/ai-market/v2/p/aimarket-nft/redeem", json={
  "token_id": "42", "contract": "0xCredits...", "wallet": "0x..."
})
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
import aimarket_nft  # adjust to package name
```

## Related plugins

See [AIMarket Hub README](../../../aimarket-hub/README.md#14-plugins) for the full plugin catalog.
