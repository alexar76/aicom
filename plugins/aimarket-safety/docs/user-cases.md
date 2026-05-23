# aimarket-safety — User Cases

### Marketplace operator

Protect all providers from jailbreak/injection without per-capability code

### Enterprise buyer

Require constitutional contract: no PII, no medical data in transit

### Auditor

Collect signed rejection receipts proving unsafe calls were blocked, not billed


## Cross-plugin workflows

| Combine with | Workflow |
|--------------|----------|
| `aimarket-channels` | Pre-fund session, run plugin features, settle once |
| `aimarket-safety` | Block unsafe calls before paid invoke |
| `aimarket-provenance` | Attach receipt to every successful invoke |
| `aimarket-reputation` | Weight search results by provider trust score |
