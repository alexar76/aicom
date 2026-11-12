# AgentAvow

> Formerly AgentGraph. The signed attestation format, JWKS, and existing badges are unchanged.

[![AgentAvow Trust](https://agentavow.com/api/v1/public/scan/AgentAvow/AgentAvow/badge)](https://agentavow.com/check/AgentAvow/AgentAvow)
[![PyPI - agentavow-trust](https://img.shields.io/pypi/v/agentavow-trust?label=agentavow-trust&color=blue)](https://pypi.org/project/agentavow-trust/)
[![Wellknown](https://wellknown.network/agents/agentavow-trust/badge.svg)](https://wellknown.network/agents/agentavow-trust)

AgentAvow answers "is this tool safe for my agent to connect?" for any tool, MCP server, package, or skill: **Safe to connect**, **Review before you connect**, or **Do not connect**, with the reason, over a **signed 0–100 trust score** you can recompute and verify offline and a separate adoption score.

## MCP Server — Trust & Security for AI Agents

Check whether a tool is safe before your agent connects to it, from Claude, ChatGPT, Cursor, VS Code or any MCP client. For a local install:

```bash
pip install agentavow-trust
```

See [sdk/mcp-server/](sdk/mcp-server/) for setup and full tool list.

### Connect from Claude

**Claude Code plugin (recommended).** The **AgentAvow Trust** plugin is listed in the Anthropic plugin directory. It bundles the MCP connector, a `/scan` command, a skill that scans a server or package before Claude adds or installs it, a SessionStart hook that checks each MCP server you have configured the first time it sees it (warn-only, fail-open), and a PreToolUse gate that checks the result on file before each MCP tool call: it denies a call to a server that reads Do not connect and asks before a tool whose definition changed since it was checked. You can also install it straight from this repo:

```
/plugin marketplace add AgentAvow/AgentAvow
/plugin install agentavow-trust@agentavow
```

Then try `/scan npm chalk`. The hook skips servers on localhost or a private network, withholds any URL whose path looks like it carries a secret, and strips credentials and query strings from a URL before it leaves your machine. [What it reads and sends](plugins/agentavow-trust/README.md#what-the-hook-reads-and-what-leaves-your-machine). Source: [plugins/agentavow-trust/](plugins/agentavow-trust/).

**Connector only.** In Claude (web or desktop), add AgentAvow from the [connector directory](https://claude.ai/directory/connectors/agentavow). In Claude Code without the plugin:

```
claude mcp add --transport http agentavow https://agentavow.com/mcp
```

### Connect from ChatGPT

AgentAvow is in the **ChatGPT plugin directory**: [add it here](https://chatgpt.com/plugins/plugin_asdk_app_6ac830ccc2d48191ac27974dec7d8344). It brings the same eight read-only tools and the trust card, plus a scan-before-connect skill. No sign-in.

### Connect from your editor

The remote MCP server is live at **`https://agentavow.com/mcp`** (Streamable HTTP, no auth, read-only) — nothing to install.

**One-click:**

- **Cursor** — `cursor://anysphere.cursor-deeplink/mcp/install?name=agentavow&config=eyJ1cmwiOiAiaHR0cHM6Ly9hZ2VudGF2b3cuY29tL21jcCJ9`
- **VS Code** — `vscode:mcp/install?%7B%22name%22%3A%20%22agentavow%22%2C%20%22type%22%3A%20%22http%22%2C%20%22url%22%3A%20%22https%3A//agentavow.com/mcp%22%7D`

**Or add it manually.** Cursor (`~/.cursor/mcp.json`, or per-project `.cursor/mcp.json`):

```json
{ "mcpServers": { "agentavow": { "url": "https://agentavow.com/mcp" } } }
```

VS Code (`.vscode/mcp.json`, or **MCP: Open User Configuration**):

```json
{ "servers": { "agentavow": { "type": "http", "url": "https://agentavow.com/mcp" } } }
```

For the local stdio server instead: `pip install agentavow-trust`.

## Key Features

- **Free, anonymous scanning** — Point AgentAvow at any GitHub repo, MCP server, npm or PyPI package, or OpenClaw skill (or a wallet address linked to an AgentAvow account) and get one of three answers back with its reason. No account, no install. Results cache for 1 hour; `?force=true` re-scans.
- **Two scores: trust + adoption** — Every scan leads with one of three answers and its reason (Safe to connect / Review before you connect / Do not connect), then a **0–100 trust score** (with a trust tier as detail) and an **adoption score** built from real usage (downloads, stars, installs). The trust score is computed from the findings; five per-category subscores (secret hygiene, code safety, data handling, filesystem access, dependency health) are reported beside it as independent axes. Each finding carries a severity and points at the exact line or manifest entry.
- **Signed, verifiable attestation** — Each result ships with a **JWS attestation** (EdDSA / Ed25519, RFC 7515) over a canonical verdict (RFC 8785 JCS). Anyone can **recompute and verify it offline** against the public JWKS at `agentgraph.co/.well-known/jwks.json` — the score is a product, the signature is the proof under it.
- **Trust tiers → recommended limits** — Each trust score maps to a trust tier (`verified` → `blocked`) with a recommended execution posture (req/min, token budget, confirmation prompts) so a gateway or agent framework can act on it automatically.
- **Trust badge** — A one-line, shields.io-compatible **SVG badge** for your README that renders the repo's current answer and signed trust score and links to the full verifiable report. Served with open CORS and refreshed from the hourly scan cache, so it never goes stale.
- **Watch & change-alerts** — Watch a tool; AgentAvow re-scans it and alerts you when its score drops or its **signed tool definition changes** (`tool_manifest_digest` drift) — the rug-pull you'd otherwise miss.
- **Claim repos you own** — Prove ownership of a public repo by adding a GitHub topic (no token stored), or run a **private scan** with a GitHub token you supply transiently (never persisted, never added to the public catalog).
- **Public trust catalog** — A paginated, filterable catalog of every scan (launch corpus plus community on-demand scans), browsable by surface, severity, and score.
- **MCP server & CI gating** — The **AgentAvow Trust** MCP server (`agentavow-trust`) exposes scanning to Claude Code and other clients, and a GitHub Action, GitLab CI component, Bitbucket Pipe, Azure Pipelines template, or local CLI can fail a build when the answer is Do not connect (`fail_on: do_not_connect`). The npm package `agentavow-trust` adds per-call gates for the Vercel AI SDK, Flue, the Claude Agent SDK and the OpenAI Agents SDK; LangChain, Google ADK, Claude Agent SDK and OpenAI Agents SDK gates for Python live in `src/bridges/`. For policy engines and gateways, [integrations/opa/](integrations/opa/) is an Open Policy Agent policy (with an Envoy `ext_authz` example) and [integrations/litellm/](integrations/litellm/) is a guardrail for LiteLLM's MCP gateway. A runnable rug-pull demo is in [demos/rugpull/](demos/rugpull/).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI, SQLAlchemy 2.0 (async), Pydantic 2.0, Uvicorn |
| **Database** | PostgreSQL 16 (asyncpg) |
| **Cache/Events** | Redis 7 (caching, rate limiting, pub/sub) |
| **Frontend** | React 19, TypeScript, Vite 7, Tailwind CSS 4, TanStack Query 5 |
| **Auth** | JWT (access + refresh tokens), API keys for agents, bcrypt |
| **Crypto/Signing** | Ed25519 (JWS/EdDSA, RFC 7515), RFC 8785 JCS canonicalization |
| **UI/Animation** | Tailwind CSS, framer-motion |
| **Infrastructure** | Docker, Docker Compose, Nginx, GitHub Actions CI |

## Quick Start

### Prerequisites

- Python 3.11+ (3.12 in production)
- Node.js 20+
- PostgreSQL 16
- Redis 7
- Docker & Docker Compose (optional, for containerized setup)

### Option 1: Docker Compose (recommended)

```bash
# Clone the repo
git clone https://github.com/AgentAvow/AgentAvow.git
cd AgentAvow

# Copy environment files
cp .env.example .env
cp .env.secrets.example .env.secrets

# Edit .env and .env.secrets with your values (see Environment Variables below)

# Start everything
docker-compose up
```

This starts:
- **Backend API** at `http://localhost:8000`
- **Frontend** at `http://localhost` (port 80)
- **PostgreSQL** at `localhost:5432`
- **Redis** at `localhost:6379`

Database migrations run automatically on startup.

### Option 2: Local Development

```bash
# Clone and enter the repo
git clone https://github.com/AgentAvow/AgentAvow.git
cd AgentAvow

# Setup Python environment, install deps, start DB services
make setup

# Copy and configure environment
cp .env.example .env
cp .env.secrets.example .env.secrets
# Edit both files with your values

# Run database migrations
make migrate

# Start the backend dev server (hot reload)
make dev
```

In a separate terminal, start the frontend:

```bash
cd web
npm install
npm run dev
```

- **Backend** runs at `http://localhost:8000`
- **Frontend** runs at `http://localhost:5173` (proxies API requests to backend)

## Environment Variables

### Required (`.env`)

```bash
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/agentgraph
POSTGRES_PASSWORD=yourpassword
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=change-me-to-a-random-64-char-string
```

### Optional (`.env`)

```bash
APP_NAME=AgentAvow
DEBUG=false
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
CORS_ORIGINS=["http://localhost:3000","http://localhost:80"]
RATE_LIMIT_READS_PER_MINUTE=100
RATE_LIMIT_WRITES_PER_MINUTE=20
RATE_LIMIT_AUTH_PER_MINUTE=5
```

### Secrets (`.env.secrets`)

```bash
ANTHROPIC_API_KEY=your_key_here   # Optional — LLM-assisted features (not required for scanning)
```

### Frontend (`web/.env`)

```bash
# Optional. Defaults to /api/v1, which the Vite dev server proxies to the backend.
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## API Overview

The public scanning API needs **no authentication**. All app endpoints use the `/api/v1` prefix; interactive API docs are at `/api/v1/docs` (Swagger) and `/api/v1/redoc` (`/docs` is the product documentation). `GET /health` (no prefix) checks DB + Redis connectivity.

### Public scan API (no auth)

| Endpoint | Path | Description |
|----------|------|-------------|
| **Scan** | `GET /public/scan/{owner}/{repo}` | Scan a repo/tool; returns the answer (`decision`) and its reason, the trust score, tier, findings, and a signed JWS attestation. `?force=true` bypasses the 1-hour cache. |
| **Badge** | `GET /public/scan/{owner}/{repo}/badge` | 20px **SVG** README badge (open CORS): the answer, the trust bar with the score, the adoption dial with the count. `?style=card` for the 360×230 card, `?style=classic` for the previous badge, `?theme=light\|dark`. Cached an hour in the browser and a day at the edge. |
| **Card** | `GET /public/scan/{owner}/{repo}/card.svg` | The trust card the `widget.js` embed shows. Cached five minutes in the browser and an hour at the edge. |
| **Checks** | `GET /public/scan/{owner}/{repo}/checks` | Adoption signals: check count, active watchers, GitHub stars, score history. |
| **History** | `GET /public/scan/{owner}/{repo}/history` | Timeline of past scans for a repo. |
| **Wallet lookup** | `GET /public/scan/wallet/{address}` | Look up a wallet linked to an AgentAvow account and scan the repo linked to it. This reads our own account records, not a chain. |
| **Catalog** | `GET /public/scan-catalog` | Paginated, filterable catalog of all scans (by surface, severity, score). |
| **OG page** | `GET /og/check/{owner}/{repo}` | Open Graph meta for a scan result page (the shareable page itself is `agentavow.com/check/{owner}/{repo}`). |

### Verification & attestations

| Endpoint | Path | Description |
|----------|------|-------------|
| **JWKS** | `GET /.well-known/jwks.json` | Public keys (EdDSA/Ed25519) for offline attestation verification. Served on `agentgraph.co`. |
| **Attestations** | `/attestations` | Issue, list, and revoke signed attestations for an entity. |
| **Security attestation** | `GET /entities/{id}/attestation/security` | Signed security-posture attestation for an entity. |
| **Composed slot** | `GET /entities/{id}/attestation/composed-slot` | `agentgraph-scan-v1-structural` slot for an APS composed-v1 envelope. |
| **Aggregate verify** | `GET /aggregate/{subject_did}/verify` | Verify a signed Trust Score v2 aggregate envelope. |

### Account (authenticated)

| Endpoint | Path | Description |
|----------|------|-------------|
| **Auth** | `/auth` | Register, login, JWT tokens, email verification |
| **Claims** | `/account/claims` | Claim a public repo you own via GitHub-topic proof (no token stored) |
| **Private scan** | `POST /account/private-scan` | Scan a private repo with a transiently-supplied GitHub token (never persisted) |
| **Watches** | `/watches` | Create/list/delete tool watches for grade + signed-definition change alerts |
| **Alert webhook** | `/account/alert-webhook` | Configure (and test) the HMAC-signed webhook that receives change alerts |

## Project Structure

```
AgentAvow/
├── src/                     # Backend (FastAPI)
│   ├── api/                 # API router modules (public scan, badge, watches, claims, attestations)
│   ├── scanner/             # Static-analysis engine + detection patterns
│   ├── signing.py           # Ed25519 signing, JWS, JCS canonicalization
│   ├── attestation/         # CTEF envelopes, APS composed slot
│   ├── trust/               # Trust score computation, aggregate envelopes, action_ref vectors
│   ├── safety/              # Anomaly / collusion / propagation controls
│   ├── source_import/       # Fetchers (GitHub, npm, PyPI, MCP, crates, Docker, HF, A2A card import, …)
│   ├── jobs/                # Scheduled jobs (watch re-scan loop, population scan)
│   ├── bridges/             # Framework adapters (MCP, LangChain, CrewAI, AutoGen)
│   ├── models.py            # SQLAlchemy models
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Settings (Pydantic)
│   ├── database.py          # Async PostgreSQL sessions
│   ├── redis_client.py      # Redis connectivity
│   ├── cache.py             # Caching layer
│   └── audit.py             # Audit logging
├── web/                     # Frontend (React + TypeScript)
│   └── src/
│       ├── rebrand/         # Live cutover UI (pages, docs, components)
│       ├── pages/           # Legacy page components
│       ├── components/      # Reusable UI components
│       ├── hooks/           # Custom React hooks
│       └── lib/             # Utilities and API client
├── ios/                     # iOS app (SwiftUI)
├── tests/                   # Test suite (pytest)
├── migrations/              # Alembic migrations
├── docker-compose.yml       # Full stack orchestration
├── Makefile                 # Development commands
└── docs/                    # PRD and architecture docs
```

## Development

### Useful Commands

```bash
make dev            # Start backend with hot reload
make test           # Run full test suite
make lint           # Lint with ruff
make lint-fix       # Auto-fix lint issues
make ast-verify     # Verify Python syntax
make migrate        # Run pending migrations
make migration      # Create a new migration
make db-start       # Start PostgreSQL + Redis (Homebrew)
make db-stop        # Stop database services
make clean          # Clean build artifacts
```

### Running Tests

```bash
# Full suite
make test

# Verbose output
.venv/bin/python3 -m pytest tests/ -v

# Single test file
.venv/bin/python3 -m pytest tests/test_auth.py -v

# With coverage
.venv/bin/python3 -m pytest tests/ --cov=src
```

### Code Standards

- **Python 3.11+** (3.12 in production) — use `from __future__ import annotations` for union types
- **Linting** — ruff (E, F, I, N, W, UP rules), 100 char line limit
- **AST verification** — all Python files must parse cleanly
- **Tests required** — all new/changed code needs unit tests

## Security

- CORS with configurable origins
- Rate limiting (read, write, auth-specific limits)
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, etc.)
- Request ID correlation for tracing
- Content filtering with HTML sanitization
- HMAC-SHA256 webhook signing
- Bcrypt password hashing
- JWT token blacklisting on logout
- Audit trail for all sensitive actions

## Architecture

AgentAvow is a layered scan-and-attest pipeline: a scan produces evidence, the evidence is scored and canonicalized, and the verdict is signed into an attestation anyone can recompute and verify offline.

```
┌─────────────────────────────────────────────────────────┐
│  Clients — check page, trust badge, MCP server, CLI,    │
│            GitHub Action, third-party verifiers         │
├─────────────────────────────────────────────────────────┤
│  Public API — /public/scan · /badge · /checks ·         │
│               scan-catalog · watches · claims           │
├─────────────────────────────────────────────────────────┤
│  Scan & score — static analysis (findings by category), │
│  per-category subscores, trust tier, adoption score,    │
│  tool-definition digests (drift / rug-pull detection)   │
├─────────────────────────────────────────────────────────┤
│  Attestation — Ed25519/JWS (RFC 7515) over a canonical  │
│  verdict (RFC 8785 JCS); CTEF envelopes; action_ref     │
├─────────────────────────────────────────────────────────┤
│  Verification — public JWKS (agentgraph.co/.well-known),│
│  offline byte-for-byte recompute, DID:web identity      │
└─────────────────────────────────────────────────────────┘
```

Watches close the loop: a background re-scan job compares each watched tool's new score and signed definition digest against the last, and fires an HMAC-signed webhook alert when either changes.

## License

Proprietary. All rights reserved.
