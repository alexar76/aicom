# aimarket-reputation — User Cases

### Consumer

Compare trust scores before opening a payment channel

### Provider

Stake USDT bond to rank higher in federated search

### Dispute auditor

Slash bond when signed consumer dispute is upheld


## Cross-plugin workflows

| Combine with | Workflow |
|--------------|----------|
| `aimarket-channels` | Pre-fund session, run plugin features, settle once |
| `aimarket-safety` | Block unsafe calls before paid invoke |
| `aimarket-provenance` | Attach receipt to every successful invoke |
| `aimarket-reputation` | Weight search results by provider trust score |
