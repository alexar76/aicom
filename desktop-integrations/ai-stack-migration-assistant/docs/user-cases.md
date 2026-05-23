# User Cases

## Case 1: Solo Developer — GPT-4 to Claude Sonnet 4.6

**User**: Alex, independent AI developer with a single Python service calling OpenAI's GPT-4.

**Situation**: Anthropic releases Claude Sonnet 4.6 with better reasoning at half the cost. Alex wants to switch but his codebase has 40+ files calling `openai.ChatCompletion.create()` with GPT-4-specific system prompts and response parsing.

**Traditional approach**: Read the Anthropic migration guide (20 pages), manually update every import, every API call, every response handler, and every error path. Estimate: 2-3 days.

**With AI Stack Migration Assistant**:

1. Alex opens his project in VSCode and runs **"AI Stack: Detect Migrations"**.
2. The extension scans for `openai` imports, discovers `gpt-4` usage patterns, and queries the hub: `"migration rules GPT-4 to Claude Sonnet 4.6"`.
3. The hub returns a rule bundle from a seller who migrated a similar codebase last week. Price: $3.00.
4. Alex previews the diff — 38 files touched, 312 insertions, 198 deletions. Every `openai.ChatCompletion.create(...)` is replaced with `anthropic.Anthropic().messages.create(...)`, response handlers are remapped from `choice.message.content` to `content[0].text`, token counting is updated.
5. Alex clicks **Apply**. The extension runs his test suite — all 47 tests pass.
6. Total time: 15 minutes. Cost: $3.00.

## Case 2: Team of 5 — LangChain 0.1 to 0.2

**User**: Data science team at a mid-size SaaS company. Their ML pipeline uses LangChain 0.1 across 12 microservices.

**Situation**: LangChain 0.2 rewrites the core API. `LLMChain` is deprecated, `load_chain()` is removed, callback system is redesigned. The team needs to upgrade before their dependency goes EOL.

**Traditional approach**: Each engineer takes 2-3 microservices. Coordination meetings. Unexpected breaks in production. Estimate: 2 weeks, high risk.

**With AI Stack Migration Assistant**:

1. Team lead installs the extension and runs bulk migration detection across all 12 repos.
2. The hub returns rules for: `"LangChain 0.1 -> 0.2 core"`, `"LangChain 0.1 -> 0.2 callbacks"`, `"LangChain 0.1 -> 0.2 chains->LCEL"`.
3. Each rule costs $2.00-$5.00. Total bill: $14.00.
4. The extension produces diffs for all 12 repos. Each engineer reviews their own diffs.
5. They batch-apply. CI catches 2 edge cases (custom callback handlers that the generic rule missed).
6. The team submits those edge cases back to the marketplace as a supplementary rule — and earns $0.50 per download.
7. Total time: 3 days (including reviews). Cost: $14.00. **Revenue potential**: ongoing passive income from the supplementary rule.

## Case 3: Startup — Switching Embedding Models

**User**: Seed-stage startup building a semantic search engine over legal documents. Currently using `text-embedding-ada-002`.

**Situation**: OpenAI announces `text-embedding-3-large` with 256x cheaper pricing and better retrieval scores. The startup needs to re-embed their entire corpus (2M documents) and update all query pipelines.

**Traditional approach**: Write a migration script by hand. Test on a sample. Run full re-embedding. Update query code. Hope nothing breaks. Estimate: 1 week of engineering time + compute costs.

**With AI Stack Migration Assistant**:

1. The CTO runs **"AI Stack: Detect Migrations"** on their embedding service repo.
2. The extension identifies `openai.Embedding.create(model="text-embedding-ada-002")` patterns and discovers a rule: `"text-embedding-ada-002 -> text-embedding-3-large"` ($4.00).
3. The rule handles:
   - Model name replacement
   - Dimensionality parameter addition (`dimensions: 1024`)
   - Response parsing update (`data[0].embedding` structure is identical but the rule validates it)
   - Token limit changes (8192 -> 8192 for v3, same)
4. Alex applies the rule. Diffs are clean.
5. The test runner fires the embedding smoke tests — they pass.
6. **Bonus**: The extension identifies that the startup's re-embedding batch job needs updating. It downloads a companion rule (`"embedding-batch-langchain-0.1"`) for $1.50 and patches the batch script.
7. Total time: 2 hours. Cost: $5.50. The re-embedding pipeline runs the same evening.

## Summary

| Case | Scenario | Traditional Time | Extension Time | Cost |
|---|---|---|---|---|
| 1 | GPT-4 -> Sonnet 4.6 (solo dev) | 2-3 days | 15 min | $3.00 |
| 2 | LangChain 0.1 -> 0.2 (5-person team) | 2 weeks | 3 days | $14.00 |
| 3 | Embedding model swap (startup) | 1 week | 2 hours | $5.50 |
