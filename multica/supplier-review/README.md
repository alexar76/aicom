# Supplier review (Multica agent)

The deterministic half of the Multica agent «ревьюер поставщиков» on attested: once a day it fetches what
modelmarket.dev publishes about its sellers (signed manifest, federation peers, observed x402 sellers), compares it
with the previous run, and checks every new or changed listing for broken schemas, prompt injection (WARDEN's static
scan and threat list), what a buyer would hand over (credentials, tokens, personal data, URLs, code, paths), and
address and price problems. The model writes the human report from `report.json` and pastes the facts block
(`report.md`) unchanged. Description: `docs/multica-use-cases.ru.md`, section 5.

- `review.mjs` — the checker (Node 22, no dependencies besides an unpacked `@aimarket/warden` ≥ 0.23.0).
- `run.sh` — downloads the three documents with curl and runs the checker; state in
  `~/.local/state/supplier-review`.
- `instructions.ru.md` — the agent's instructions as set in Multica.
- `review.test.mjs` — `node --test multica/supplier-review/review.test.mjs` (needs `warden/dist`).

On attested the files live in the daemon container under `/home/node/tools/{supplier-review,warden}` (owned by
another user, read-only for the agent). The agent's Multica environment disables the hub MCP servers
(`OPENCODE_CONFIG_CONTENT`) and blanks the hub keys and `GH_TOKEN`.
