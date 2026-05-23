# Architecture

Local Security Audit is a **Tauri v2 desktop application** with a Rust backend that performs local git repository scanning and integrates with the AI Market Protocol for security intelligence feeds.

## High-level overview

```
┌──────────────────────────────────────────────────┐
│                   Tauri Shell                     │
│  ┌────────────────────────────────────────────┐  │
│  │        WebView Frontend (React)            │  │
│  │  Dashboard  ·  Scan Results  ·  Settings   │  │
│  └───────────────────┬────────────────────────┘  │
│                      │ IPC (invoke)               │
│  ┌───────────────────▼────────────────────────┐  │
│  │            Rust Backend (Tauri)             │  │
│  │                                             │  │
│  │  ┌──────────────────┐  ┌────────────────┐  │  │
│  │  │  Git Scanner     │  │  Rule Engine    │  │  │
│  │  │  - libgit2       │  │  - CVE matcher │  │  │
│  │  │  - commit walk   │  │  - secret rx   │  │  │
│  │  │  - blob parsing  │  │  - dep check   │  │  │
│  │  └──────────────────┘  └───────┬────────┘  │  │
│  │                                │            │  │
│  │  ┌─────────────────────────────▼──────────┐ │  │
│  │  │  Marketplace Integration               │ │  │
│  │  │  (aimarket-agent SDK)                   │ │  │
│  │  │  - discover capabilities               │ │  │
│  │  │  - open payment channel                │ │  │
│  │  │  - invoke / buy feeds                  │ │  │
│  │  │  - close & settle                      │ │  │
│  │  └────────────────────────────────────────┘ │  │
│  │                                             │  │
│  │  ┌────────────────────────────────────────┐ │  │
│  │  │  TEE Verifier                          │ │  │
│  │  │  - attestation validation              │ │  │
│  │  │  - code hash trust store               │ │  │
│  │  │  - receipt verification                │ │  │
│  │  └────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

## Component breakdown

### 1. Tauri Desktop Shell

The Tauri shell manages the webview frontend and provides OS-level capabilities: file system access (to browse local git repos), native menus, system tray, and background scanning.

- **Frontend**: React with Tailwind CSS. Communicates with the Rust backend via Tauri's `invoke` IPC.
- **Commands exposed to frontend**:
  - `scan_repo(path)` — triggers a full scan
  - `discover_feeds(category, budget)` — marketplace discovery
  - `buy_feed(capability_id, channel_id)` — purchase a rule feed
  - `get_results()` — returns the latest scan report
  - `export_report(format)` — export as JSON/HTML/SARIF

### 2. Local Git Scanning Engine

Built on [`git2`](https://crates.io/crates/git2) (libgit2 bindings). The engine never sends data over the network.

**Scan operations**:

| Operation | Description |
|-----------|-------------|
| **Commit walk** | Enumerate all commits in HEAD's reachable history |
| **Blob content scan** | Regex and entropy-based secret detection on file blobs |
| **Dependency parsing** | Parse `package.json`, `Cargo.toml`, `go.mod`, `Gemfile`, `requirements.txt` |
| **Git config audit** | Check for exposed credentials in `.git/config` and `url.*.insteadOf` |
| **Anti-pattern detection** | Flag hardcoded API keys, private keys, AWS ARNs, JWT tokens, etc. |

**Privacy guarantee**: All scanning happens in-process on the local machine. No file contents, commit messages, or repository metadata are ever transmitted.

### 3. Marketplace Integration (Rust SDK)

The `aimarket-agent` crate handles all interaction with the AI Market Hub.

**Protocol phases**:

1. **Discovery** — search for available security capabilities: CVE feeds, exploit DB dumps, secret-scanning rule sets
2. **Channel open** — deposit funds into a payment channel (USDT on supported chains)
3. **Invoke** — purchase a rule feed. The response includes a TEE attestation proving the feed was generated in a verified enclave
4. **Close & settle** — finalize payment and receive a settlement receipt

All purchases are recorded locally in a SQLite ledger for audit trail.

### 4. TEE for Verified CVE Accuracy

When purchasing CVE feeds or exploit DB data, the marketplace returns:

- **TeeAttestation** — signed proof that the response was computed inside a TEE (AWS Nitro, Intel TDX, or AMD SEV)
- **TeeReceipt** — input/output hash signed by the enclave, verifiable client-side

The app verifies attestations using the `TeeVerifier` from the SDK. This ensures:

- The CVE data was not tampered with in transit
- The marketplace compute ran the exact code it claims
- The response timestamp is within the attestation TTL

### 5. Signature Marketplace (Sell Side)

When the scanner finds an anti-pattern (e.g., a hardcoded credential pattern), it:

1. Extracts the **signature** — a hash of the pattern context (file type, code structure, surrounding AST)
2. **Never** includes the actual credential or source code
3. Optionally lists the signature on the marketplace with metadata (severity, ecosystem, pattern category)

Buyers receive signature hashes only. There is no way to reverse the hash to recover original source code.

### 6. Rule Cache & Offline Mode

Rules purchased from the marketplace are cached locally in `~/.local-security-audit/cache/`:

- Rules are serialized as MessagePack for fast loading
- Cache entries include the TEE receipt for auditability
- Stale entries are flagged; the user is prompted to refresh

In offline mode, the app works exclusively from the cache.

## Data flow

```
User selects repo path
        │
        ▼
Git Scanner opens repo (libgit2)
        │
        ├──► Enumerate commits
        ├──► Parse dependency manifests
        ├──► Scan blobs for secrets
        └──► Build dependency tree
                │
                ▼
        Rule Engine loads cached rules
        (or prompts user to buy fresh feeds)
                │
                ▼
        Marketplace SDK: discover + buy
                │
                ▼
        TEE verification of purchased feeds
                │
                ▼
        Cross-reference findings against rules
                │
                ▼
        Generate report (critical/high/medium/low)
                │
                ▼
        Display in frontend + offer export
```

## Key dependencies

| Crate | Purpose |
|-------|---------|
| `tauri` | Desktop app framework |
| `aimarket-agent` | AI Market Protocol consumer SDK |
| `git2` | Local git repository access |
| `serde` / `serde_json` | Serialization |
| `sled` or `rusqlite` | Local cache and ledger |
| `regex` | Pattern-based secret detection |
| `entropy` | High-entropy string detection |
| `chrono` | Timestamp handling |
| `ring` | Cryptography for signature hashing |

## Security & privacy

- **Code never leaves the device** — all scanning is local
- **Only signature hashes are sellable** — no source code is ever transmitted
- **TEE-verified marketplace purchases** — attestation receipts prove feed integrity
- **Encrypted local cache** — rules are stored with AES-GCM using a device-derived key
- **No telemetry** — the app does not phone home except for marketplace interactions
