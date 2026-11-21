First release: what your MCP servers cost in tokens before you type a word.

```bash
npx mcp-token-cost
```

- Every MCP server in the configs of Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, Gemini CLI and Codex,
  read live (stdio, streamable HTTP, HTTP+SSE) or `--offline` from HISTOR's public record, nothing started.
- Per server and per tool, split into name, description, input schema and structure; heaviest schema property;
  server instructions on their own line. Counted the way HISTOR counts, to the token.
- Each server's rank among every listed MCP server with a current tool list in HISTOR's snapshot of 2026-11-16.
- Findings that break the prompt cache (a tool list whose order or content changes between reads, dates and UUIDs
  in definitions) or waste tokens (repeated sentences, huge enums, deep schemas, duplicate tool names), sized in
  tokens per request.
- `--claude`: Claude's own count through Anthropic's token counting API, including its tool-use prompt.
- Reports in text, JSON, Markdown, self-contained HTML and SARIF; price per 1,000 requests.
- CI: `snapshot` / `check` / `diff` with each measure checked on its own, a noise floor and a budget; this repository
  is also a GitHub Action (`uses: alexar76/mcp-token-cost@v0.1.0`).

Full list: [CHANGELOG.md](CHANGELOG.md).
