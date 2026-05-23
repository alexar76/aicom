# Architecture

Interview Prep Coach is a Flutter desktop application that uses the `aimarket_agent` Dart SDK to discover, purchase, and invoke interview preparation capabilities from the AI Market decentralized protocol.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Interview Prep Coach App                       │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │  Prep Tab  │  │ Market Tab │  │ History Tab│  │Community Tab│ │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘ │
│        │               │               │               │        │
│  ┌─────▼───────────────▼───────────────▼───────────────▼──────┐ │
│  │                    App State (Provider)                     │ │
│  │  - onboarding status   - target company/role               │ │
│  │  - theme preferences   - marketplace connection state       │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                             │                                    │
│  ┌──────────────────────────▼──────────────────────────────────┐ │
│  │                  MarketplaceService                          │ │
│  │  ┌─────────────────────────────────────────────────────┐    │ │
│  │  │   discoverInterviewQuestions(company, role)          │    │ │
│  │  │   discoverRecentSignals(company)                     │    │ │
│  │  │   ensureChannel(depositUsd)                          │    │ │
│  │  │   getInterviewQuestions(capabilityId, input)         │    │ │
│  │  │   submitAnonymizedTrajectory(trajectory)             │    │ │
│  │  │   verifyAttestation(attestation, capabilityId)      │    │ │
│  │  └──────────────────────────┬──────────────────────────┘    │ │
│  └─────────────────────────────┼───────────────────────────────┘ │
│                                │                                 │
│  ┌─────────────────────────────▼───────────────────────────────┐ │
│  │                 aimarket_agent Dart SDK                      │ │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐ ┌──────┐ │ │
│  │  │Discover  │ │ Channel  │ │ Invoke  │ │Settle │ │Verify│ │ │
│  │  │agent.dis │ │agent.open│ │agent.in │ │agent. │ │agent.│ │ │
│  │  │ cover()  │ │Channel() │ │ voke()  │ │close  │ │verify│ │ │
│  │  │          │ │          │ │         │ │Channel│ │Tee() │ │ │
│  │  └──────────┘ └──────────┘ └─────────┘ └───────┘ └──────┘ │ │
│  └─────────────────────────────┬───────────────────────────────┘ │
└────────────────────────────────┼─────────────────────────────────┘
                                 │ HTTP/HTTPS
                    ┌────────────▼────────────┐
                    │     AI Market Hub        │
                    │   (hub.aicom.io)         │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │ Capability Registry│  │
                    │  │ Payment Channels   │  │
                    │  │ TEE Attestation    │  │
                    │  │ Safety Gates       │  │
                    │  └────────────────────┘  │
                    └──────────────────────────┘
```

---

## Five-Phase Marketplace Cycle

Interview Prep Coach follows the AI Market Protocol's 5-phase consumer cycle on every marketplace interaction:

```
Phase 1          Phase 2          Phase 3          Phase 4          Phase 5
DISCOVER         CHANNEL          INVOKE           SETTLE           VERIFY

   │                │                │                │                │
   │  Search        │  Open          │  Pay            │  Close         │  Check
   │  capabilities  │  pre-funded    │  & execute      │  channel       │  TEE
   │  by intent     │  channel       │  capability     │  get refund    │  receipt
   │                │                │                │                │
   ▼                ▼                ▼                ▼                ▼

┌────────┐    ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐
│agent.  │    │agent.  │     │agent.  │     │agent.  │     │agent.  │
│discover│───►│open    │────►│invoke  │────►│close   │────►│verify  │
│(intent)│    │Channel │     │(capId, │     │Channel │     │Tee     │
│        │    │(5.00)  │     │ input) │     │(id)    │     │Receipt │
└────────┘    └────────┘     └────────┘     └────────┘     └────────┘
                                                                   
   ▲                                                                
   │                          ┌─────────────┐                      
   └──────────────────────────│BillOfMaterials│──────────────────────┘
                              │  - plan      │
                              │  - results   │
                              │  - settlement│
                              │  - totalSpent│
                              └─────────────┘
```

### Phase 1: Discovery

**What happens**: The app sends an intent-based search query to the hub. The hub matches against capability metadata and returns ranked results.

**Protocol call**: `GET /ai-market/v2/search?intent=...&budget_usd=...&category=career`

**Interview Prep Coach usage**:
```dart
final plan = await marketplace.discoverInterviewQuestions(
  company: 'Google',
  role: 'Software Engineer',
  focusArea: 'behavioral',
  budget: 5.00,
);
```

**Response**: A list of `PlanStep` objects, each containing a `Capability` with:
- `capability_id` (e.g., `google-swe-q3-2026`)
- `product_id` (e.g., `google-swe-q3-2026`)
- `name`, `version`, `description`
- `price_per_call_usd` (e.g., $0.10)
- `trust_score` (e.g., 0.95)
- `source_hub` (federated hub URL)
- `input_schema`, `output_schema`

### Phase 2: Channel Open

**What happens**: The app opens a pre-funded payment channel with a deposit. This creates a balance that the hub debits per invocation.

**Protocol call**: `POST /ai-market/v2/channel/open`

**Interview Prep Coach usage**:
```dart
final channel = await marketplace.ensureChannel(depositUsd: 5.00);
```

**Economics**: A $5.00 channel deposit on Base chain in USDT/USDC covers approximately 50 question bank calls at $0.10 each. Unused balance is refunded when the channel is closed.

### Phase 3: Invoke

**What happens**: The app calls a specific capability, paying from the channel. The hub verifies payment, executes the capability (typically inside a TEE), and returns results.

**Protocol call**: `POST /ai-market/v2/invoke`

**Interview Prep Coach usage**:
```dart
final result = await marketplace.getInterviewQuestions(
  capabilityId: 'google-swe-q3-2026',
  input: {
    'target_role': 'Software Engineer',
    'years_experience': 4,
    'focus_areas': ['leadership', 'conflict_resolution'],
  },
);
```

**Response**: An `InvokeResult` containing:
- `output`: The interview questions and suggested answers
- `price_usd`: Cost of this invocation
- `latency_ms`: Execution time
- `tee_verified`: Whether TEE attestation was verified
- `tee_receipt`: Proof of TEE execution
- `safety_blocked`: Whether the request was blocked by safety gates

### Phase 4: Settle

**What happens**: The app closes the payment channel. The hub settles accounts and refunds any unused balance.

**Protocol call**: `POST /ai-market/v2/channel/close`

**Interview Prep Coach usage**:
```dart
final settlement = await marketplace.closeChannel();
print('Spent: \$${settlement.totalSpentUsd}');
print('Refunded: \$${settlement.refundUsd}');
```

### Phase 5: Verify

**What happens**: The app verifies TEE attestation and receipts to prove that:
1. The capability ran inside a secure enclave (pre-invocation check).
2. The output was genuinely produced by that enclave (post-invocation check).

**Interview Prep Coach usage**:
```dart
// Pre-invocation: verify the capability runs in a TEE
final attestationVerified = agent.verifyTeeAttestation(
  attestation, capabilityId,
);

// Post-invocation: verify output was produced in the TEE
final receiptVerified = agent.verifyTeeReceipt(
  result.teeReceipt!, inputJson, outputJson,
);
```

---

## TEE Verification Flow

Trusted Execution Environment (TEE) verification is critical for interview prep because:

- **Question banks are valuable IP**: Sellers need assurance their content isn't stolen.
- **Answers are personal**: Buyers need assurance their data is processed privately.
- **Trajectories must be authentic**: The marketplace needs proof that submissions are genuine.

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│  Buyer App  │         │  AI Market  │         │  Seller     │
│  (Flutter)  │         │  Hub        │         │  Capability │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │                       │                       │
       │  1. Discover          │                       │
       │──────────────────────►│                       │
       │                       │                       │
       │  2. Return manifest   │                       │
       │  (includes TEE        │                       │
       │   attestation)        │                       │
       │◄──────────────────────│                       │
       │                       │                       │
       │  3. Verify locally:   │                       │
       │  - Check expiry       │                       │
       │  - Check code hash    │                       │
       │  - Verify platform    │                       │
       │   sig                 │                       │
       │                       │                       │
       │  4. Open channel      │                       │
       │──────────────────────►│                       │
       │                       │                       │
       │  5. Invoke (signed    │                       │
       │     + encrypted)      │                       │
       │──────────────────────►│──────────────────────►│
       │                       │                       │
       │                       │  6. Execute in TEE   │
       │                       │  - Decrypt input     │
       │                       │  - Run capability    │
       │                       │  - Sign output       │
       │                       │◄──────────────────────│
       │                       │                       │
       │  7. Return result     │                       │
       │  + TEE receipt        │                       │
       │◄──────────────────────│                       │
       │                       │                       │
       │  8. Verify receipt:   │                       │
       │  - input_hash matches │                       │
       │  - output_hash matches│                       │
       │  - signature valid    │                       │
       │                       │                       │
       │  9. Close channel     │                       │
       │──────────────────────►│                       │
       │                       │                       │
```

### Attestation Verification (Client-Side)

The `TeeVerifier` in the Dart SDK performs three checks:

1. **Expiry**: Attestations have a TTL (default 300 seconds). Expired attestations are rejected.
2. **Code hash**: The capability's code hash is compared against a trusted registry. Mismatches are flagged.
3. **Platform signature**: The enclave's signature is verified against well-known platform public keys (AWS Nitro, Intel TDX, AMD SEV-SNP).

```dart
// From the SDK's TeeVerifier:
bool verifyAttestation(TeeAttestation attestation, String capabilityId) {
  if (attestation.isExpired) return false;
  final expectedHash = _trustedCodeHashes[capabilityId];
  if (expectedHash != null && attestation.codeHash != expectedHash) return false;
  final enclaveKey = _enclavePublicKeyForPlatform(attestation.platform);
  if (enclaveKey == null) return false;
  return _signer.verify(enclaveKey, attestation.signature, attestation.canonical);
}
```

### Receipt Verification (Client-Side)

After invocation, the user can verify that the exact input they sent was processed and the exact output they received was produced inside the attested enclave:

```dart
bool verifyReceipt(TeeReceipt receipt, String expectedInput, String receivedOutput) {
  final inputHash = sha256.convert(utf8.encode(expectedInput)).toString();
  final outputHash = sha256.convert(utf8.encode(receivedOutput)).toString();
  if (receipt.inputHash != inputHash) return false;
  if (receipt.outputHash != outputHash) return false;
  return true; // Plus signature verification against enclave key.
}
```

---

## Privacy Architecture

Interview Prep Coach implements a "privacy by design" architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    User's Device                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           Local Processing (on-device)            │   │
│  │  ┌────────────┐  ┌──────────────────────────┐   │   │
│  │  │Practice    │  │ PII Stripper              │   │   │
│  │  │Session     │  │ - Removes name/email/phone│   │   │
│  │  │(answers    │  │ - Hashes company names    │   │   │
│  │  │ stay here) │  │ - Reduces location to     │   │   │
│  │  └────────────┘  │   region only             │   │   │
│  │                  └───────────┬──────────────┘   │   │
│  └──────────────────────────────┼──────────────────┘   │
│                                 │                       │
│  ┌──────────────────────────────▼──────────────────┐   │
│  │     Encrypted & Signed Marketplace Request       │   │
│  │  - Input encrypted for TEE (seller can't see)   │   │
│  │  - Payment signed with channel key              │   │
│  │  - PII already stripped client-side              │   │
│  └──────────────────────┬──────────────────────────┘   │
└─────────────────────────┼──────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────┐
│                    AI Market Hub                        │
│  - Routes request to capability seller                 │
│  - Deducts payment from channel                        │
│  - Returns TEE receipt                                 │
└─────────────────────────────────────────────────────────┘
```

### Data at Rest

- Wallet keys: Stored in `shared_preferences` (development) or OS keychain (production).
- Practice answers: Stored in local SQLite database via `sqflite_common_ffi`.
- Purchased question banks: Cached locally after purchase.
- Trajectory submissions: Uploaded only after PII stripping and user confirmation.

### Data in Transit

- All marketplace communications go over HTTPS.
- Capability inputs are encrypted for TEE execution (seller cannot read the input).
- Payment channel signatures prevent replay attacks.

---

## State Management

The app uses `Provider` for state management:

```
┌─────────────────────────────────────────────────────────┐
│  ChangeNotifierProvider<AppState>                        │
│  - onboardingComplete: bool                             │
│  - targetCompany: String?                                │
│  - targetRole: String?                                   │
│  - themeMode: ThemeMode                                  │
│  - marketplaceConnected: bool                            │
│  + loadPersistedState()                                  │
│  + completeOnboarding()                                  │
│  + setTarget(company, role)                              │
│  + setThemeMode(mode)                                    │
│  + setMarketplaceConnected(bool)                         │
└─────────────────────────────────────────────────────────┘
```

Services are provided as simple `Provider` instances (not `ChangeNotifierProvider`) since they manage external resources:

```dart
Provider(create: (_) => WalletService()),
Provider(create: (_) => MarketplaceService(hubUrl: 'https://hub.aicom.io')),
```

---

## Dependency Graph

```
pubspec.yaml
├── flutter (SDK)
├── aimarket_agent (path: ../aimarket-sdks/dart)
│   ├── http
│   ├── crypto
│   └── (Ed25519 in production)
├── sqflite_common_ffi (local database)
├── provider (state management)
├── shared_preferences (key-value storage)
├── url_launcher (external links)
├── intl (localization)
└── flutter_svg (vector icons)
```

The `aimarket_agent` package is the only external service dependency. All other dependencies are either Flutter SDK packages or local data management.
