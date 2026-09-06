# SDK version policy

AIMarket ships **four consumer SDKs** across two semver lines. Version numbers are **not** tied to protocol version — all target **AIMarket Protocol v2**.

---

## Package matrix

| Package | Registry | Version line | Current |
|---------|----------|--------------|---------|
| `aimarket-agent` | [PyPI](https://pypi.org/project/aimarket-agent/) | Python line | **2.1.x** |
| `@aimarket/agent` | [npm](https://www.npmjs.com/package/@aimarket/agent) | Multi-lang line | **0.2.x** |
| `aimarket_agent` | [pub.dev](https://pub.dev/packages/aimarket_agent) | Multi-lang line | **0.2.x** |
| `aimarket-agent` (crate) | [crates.io](https://crates.io/crates/aimarket-agent) | Multi-lang line | **0.2.x** |

---

## Why two lines?

| Line | Rationale |
|------|-----------|
| **Python 2.x** | Shipped first with CLI, `run()` loop, BOM audit trail, hub-trust channels — no wallet in public API. |
| **Multi-lang 0.2.x** | Dart, TypeScript, Rust launched together with **Ed25519 invoke signing** (plus an optional secondary EIP-712/secp256k1 key for on-chain channel debits). Versions are **lock-stepped** in CI. |

**Both are supported.** Choose by runtime:

| Your app | Install |
|----------|---------|
| LangChain / server agent / CLI | `pip install aimarket-agent` |
| Flutter | `dart pub add aimarket_agent` |
| Electron / Node | `npm install @aimarket/agent` |
| Tauri / Rust | `aimarket-agent = "0.2.0"` |

---

## Release triggers

| Package | Trigger | Workflow repo |
|---------|---------|---------------|
| Python SDK | GitHub Release | `alexar76/aimarket-agent` |
| npm / pub.dev / crates.io | Tag `v*` | `alexar76/aimarket-sdks` |

Manual: `./scripts/publish_pypi.sh aimarket-agent`

---

## Future alignment

Python may move to **3.x** when the public API adds explicit wallet + signing (Ed25519 / optional EIP-712) parity with the multi-lang SDKs. Until then **2.x + 0.2.x** is intentional.

Integration guides: [`aimarket-sdks/README.md`](https://github.com/alexar76/aimarket-sdks/blob/main/README.md) · [`aimarket-agent/README.md`](https://github.com/alexar76/aimarket-agent/blob/main/README.md)
