# Personal Finance Coach — Architecture

## Design Principle

**Bank statements never leave the device.** All parsing, categorization, and budgeting runs locally. The marketplace delivers rules IN; only anonymized cohort patterns flow OUT.

## Layers

```
┌─────────────────────────────────────────────────────┐
│  Presentation Layer (Flutter)                       │
│  Dashboard │ Import │ Budget │ Tax │ Marketplace     │
├─────────────────────────────────────────────────────┤
│  Domain Services (Dart)                             │
│  CsvParser │ Categorizer │ BudgetCalc │ TaxEst      │
├─────────────────────────────────────────────────────┤
│  Marketplace Integration (aimarket_agent SDK)       │
│  discover() │ openChannel() │ invoke() │ settle()   │
├─────────────────────────────────────────────────────┤
│  Local Storage (SQLite)                             │
│  transactions │ categories │ budgets │ tax_rules    │
├─────────────────────────────────────────────────────┤
│  Privacy Layer                                       │
│  Anonymizer │ zk-proof generator │ TEE verifier     │
└─────────────────────────────────────────────────────┘
```

## Data Flow

### Buying Tax Rules
1. User sets jurisdiction (e.g., "US-CA")
2. `AimarketAgent.discover(intent: "tax rules US California 2026")`
3. `agent.openChannel(5.00)`
4. `agent.invoke(capabilityId: "ca-tax-rules-2026", input: {...})`
5. Rules stored in local SQLite
6. `agent.closeChannel(channelId)`

### Selling Cohort Patterns
1. User opts in: "Share anonymized spending patterns"
2. Local categorizer aggregates user's transactions
3. Anonymizer strips all PII — only `{age_bracket, city_tier, category, pct_of_income}` remains
4. zk-proof generated: proves user is in cohort without revealing raw data
5. `agent.invoke(capabilityId: "publish-cohort-pattern", input: {pattern, zk_proof})`
6. Hub verifies zk-proof, credits user's wallet

## Privacy Boundary

| Data | Location | Shared? |
|---|---|---|
| Raw bank CSV | Local disk only | Never |
| Parsed transactions | Local SQLite | Never |
| Category labels | Local SQLite | Never |
| Monthly spending totals | Local SQLite | Never |
| Anonymized cohort pattern | Hub | Yes (with zk-proof) |
| Tax rule results | Local SQLite | Never (rules come IN) |

## Security

- Wallet private key stored in OS keychain (macOS Keychain / Windows Credential Manager)
- All marketplace calls signed with Ed25519
- TEE attestation verified before accepting purchased rules
- zk-proof generated locally before any data leaves device
