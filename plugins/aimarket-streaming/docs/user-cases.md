# aimarket-streaming — User Cases

### Chat UI

Bill per token chunk instead of flat per-response fee

### Long reports

Stop stream early; pay only for generated tokens

### Live coding agent

Micro-receipt after each SSE event for audit trail


## Cross-plugin workflows

| Combine with | Workflow |
|--------------|----------|
| `aimarket-channels` | Pre-fund session, run plugin features, settle once |
| `aimarket-safety` | Block unsafe calls before paid invoke |
| `aimarket-provenance` | Attach receipt to every successful invoke |
| `aimarket-reputation` | Weight search results by provider trust score |
