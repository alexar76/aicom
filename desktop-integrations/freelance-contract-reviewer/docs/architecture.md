# Architecture — Freelance Contract Reviewer

## Overview

The Freelance Contract Reviewer is a privacy-first Flutter desktop application that integrates with the AI Market Protocol v2 marketplace. It follows a **local-first** architecture: contract documents are parsed and analyzed on-device, and only anonymized clause fragments are sent to the marketplace for rule-based evaluation inside a Trusted Execution Environment (TEE).

---

## System layers

```
┌─────────────────────────────────────────────────┐
│                Presentation Layer                 │
│  Flutter widgets: Dashboard, Upload, Review,     │
│  Marketplace Browser, Sell Pattern               │
├─────────────────────────────────────────────────┤
│                Domain Services                    │
│  ContractParser  │  ClauseAnonymizer  │  Reporter │
├─────────────────────────────────────────────────┤
│            Marketplace Integration                │
│  AimarketAgent  │  PaymentChannel  │  TEE Verify │
├─────────────────────────────────────────────────┤
│            External (AI Market Hub)               │
│  Discovery  │  TEE Enclave  │  Settlement        │
└─────────────────────────────────────────────────┘
```

---

## 1. Presentation Layer

Standard Flutter widget tree. Three main views:

- **Dashboard** (`lib/screens/dashboard_screen.dart`): recent contracts, quick stats, marketplace recommendations.
- **Review** (`lib/screens/review_screen.dart`): clause-by-clause evaluation with severity indicators.
- **Marketplace** (`lib/screens/marketplace_screen.dart`): library discovery, purchase, and anonymized selling.

---

## 2. Domain Services

### Contract Parser

```
Input:  PDF / DOCX / TXT file
Process: Local extraction via pdf_text, docx_to_text, or raw text parsing
Output: List<Clause> — structured AST of contract clauses
```

- Runs entirely in-process on the user's machine.
- Uses regex-based section detection to split contracts into clauses (scope of work, payment, IP, non-compete, termination, etc.).
- No network calls. No cloud dependency.
- File types supported via pure-Dart parsers or FFI:
  - `.pdf` → `pdf_text` package or Poppler-based extraction
  - `.docx` → `archive` + XML parsing
  - `.txt` → raw text

### Clause Anonymizer

```
Input:  Clause AST (with party names, dates, amounts)
Process: Regex + NLP-based NER replacement
Output: Anonymized clause AST
```

Before any clause data leaves the machine, the anonymizer:

1. Detects and replaces: party names, dollar amounts ($X.XX → `{amount}`), dates, addresses, company names.
2. Preserves clause structure and legal language (the "shape" of the clause).
3. Generates an anonymization report showing what was changed.
4. User must explicitly approve the anonymized version before marketplace submission.

### Reporter

Generates a structured review report:

```
ContractReview {
  clauses: List<ClauseResult> {
    type: "payment_terms" | "ip_ownership" | "non_compete" | ...,
    text: string,
    risk: "low" | "medium" | "high",
    matched_rules: List<MatchedRule>,
    suggestion: string
  },
  overall_risk: "low" | "medium" | "high",
  total_issues: int,
  library_used: string  // purchased capability ID
}
```

---

## 3. Marketplace Integration (SDK)

Uses `AimarketAgent` from the `aimarket_agent` Dart SDK. See [sdk-integration.md](sdk-integration.md) for detailed code examples.

### Flow

```
1. SEARCH  →  discover(intent: "California freelance IP clause library", budget: 5.00, category: "legal")
2. CHANNEL →  openChannel(5.00)
3. VERIFY  →  TEE attestation check on selected capability
4. INVOKE  →  invoke(capabilityId, input: anonymizedClauses, channelId)
5. SETTLE  →  closeChannel(channelId)
6. (OPTIONAL) SELL → invoke with product for anonymized pattern submission
```

### Privacy boundary

```
┌───────────────────────────────────┐
│ User Machine (untrusted hub sees) │
├───────────────────────────────────┤
│ Full contract text       ─── NO   │
│ Anonymized clause text   ─── YES  │
│ Clause type                     │
│ (e.g. "arbitration_clause")      │
│ PII (names, $$, dates)  ─── NO   │
│ TEE attestation check   ─── YES  │
│ TEE receipt             ─── YES  │
└───────────────────────────────────┘
```

---

## 4. TEE Flow

The privacy guarantee depends on TEE attestation:

1. **Before purchase**: app fetches the capability manifest from the hub. Manifest includes the TEE attestation (AWS Nitro enclave measurements).
2. **Attestation verification**: `AimarketAgent.verifyTeeAttestation()` checks:
   - The attestation is not expired (5-minute TTL).
   - The code hash matches the expected library code.
   - The enclave signature is valid against the hub's well-known key.
3. **Invoke**: anonymized clause text is sent to the TEE endpoint.
4. **Receipt verification**: after receiving results, `AimarketAgent.verifyTeeReceipt()` confirms the output was produced inside the attested enclave.

This guarantees that even the marketplace operator cannot read your clause text — only the purchased library code inside the enclave can.

---

## 5. Data model

```
User (local only)
├── wallet_key: string (encrypted at rest)
├── contracts: List<Contract>
│   ├── id: UUID
│   ├── filename: string
│   ├── uploaded_at: DateTime
│   ├── status: "pending" | "reviewed"
│   ├── clauses: List<Clause>
│   └── report: ContractReview?
└── purchases: List<LibraryPurchase>
    ├── capability_id: string
    ├── price_usd: double
    └── purchased_at: DateTime
```

---

## 6. Security considerations

| Concern | Mitigation |
|---------|-----------|
| Wallet key storage | Encrypted with platform-specific keychain (flutter_secure_storage) |
| Contract data on disk | SQLite database with `PRAGMA key` encryption |
| Network interception | HTTPS + signed payment headers |
| Malicious hub | TEE attestation verification + code hash pinning |
| Malicious library | Code hash trust registry — only known-good hashes accepted |
