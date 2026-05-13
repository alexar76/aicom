# AI-Factory: I Built an Open-Source Pipeline That Turns Ideas Into Products Using 18 AI Agents

**TL;DR** — MIT-licensed, self-hosted pipeline that takes a plain-language idea and runs it through 18 specialized AI agents (PM, Architect, Developer, QA, Security, etc.) with quality gates, auto-failover between LLM providers, and a full admin panel.

---

## The Problem

AI code generators are everywhere — Bolt.new, Lovable, v0, Devin. They're great for demos. But every single one has the same issues:

1. **Vendor lock-in** — generated code stays on their platform
2. **No quality checks** — they ship whatever the LLM outputs, including broken stubs
3. **Cloud-only** — your API keys, your prompts, your data go through their servers
4. **Single agent** — one LLM call for everything, no specialization

I wanted something different. Something self-hosted, open-source, with actual quality gates and specialized agents that work together like a real team.

## What I Built

**AI-Factory** — an autonomous product pipeline that turns one sentence into a shippable web page or full-stack application.

### The Pipeline

```
💡 Idea → 🔍 Discovery → 📋 Analyst → 📝 PM → 🎨 Architect → 
👨‍💻 Developer → 🧪 QA + E2E → 🔒 Security → 🚀 DevOps → 
📢 Marketing → 💰 Sales → 🔄 Evolution
```

### 18 Specialized Agents

Each agent has a specific role and validates its input/output:

| Agent | Role |
|-------|------|
| Analyst | Market research, competitive context |
| PM | Product specifications from ideas |
| Architect | System architecture + UX direction |
| Design Critic | Optional art-direction gate |
| Developer | Code generation |
| Hardening | Stability pass |
| QA | Automated testing, static analysis |
| Security | Vulnerability scanning |
| DevOps | Docker/K8s, CI/CD |
| Marketing | Go-to-market strategy |
| Sales | Pricing tiers |
| Evolution Analyst | Post-ship improvements |

### 5 Quality Gates (The Secret Sauce)

Most AI generators ship whatever the LLM outputs. AI-Factory has **hard pass/fail gates**:

1. **Demo Quality** — 12 checkpoints (contrast, CTAs, broken links, spec coverage)
2. **Browser E2E** — Playwright crawl (desktop + mobile 390×844), JS errors, 404s
3. **Visual QA** — 9 heuristics (contrast ratio, CSS vars, empty states, nav interactivity)
4. **Security** — AST scan for eval(), innerHTML, exposed tokens, hardcoded secrets
5. **Methodology** — Domain-specific packs (fintech, ecommerce, healthcare, etc)

Without these, the pipeline produces "pretty but broken" output — a beautiful landing with a non-functional form, or a full-stack app with hardcoded API keys.

### LLM Router with Auto-Failover

The router supports **6+ providers** (DeepSeek, Anthropic, OpenAI, Ollama, Groq, Together AI) with:
- Health checks every 60 seconds
- Automatic failover when a provider goes down
- Task-level pinning (heavy tasks stick to the primary provider)
- Semantic response caching

### State Machine with Recovery

11 strict states with 34 valid transitions, dual persistence (JSON + SQLite), and recovery paths:
- If JSON parse fails, fall back to SQLite snapshot
- If a task times out, auto-requeue with backoff
- If the model hallucinates a file path, recover and retry

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python FastAPI + Uvicorn |
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| Container | Docker (Python 3.11 + Node.js 20) |
| State | SQLite + JSON dual persistence |
| Monitoring | Prometheus + Grafana (14 panels) |
| Security | JWT auth, TOTP 2FA, audit logging |
| LLM | Pluggable provider system |

## Numbers

- **62,000+** lines of Python
- **20,000+** lines of TypeScript/TSX
- **278** Python files
- **72+** test files
- **150+** commits
- **18** agents in the pipeline
- **5** quality gates
- **6+** LLM providers with auto-failover
- **1** autonomous Director AI managing everything

## Why Open Source (MIT)?

Because vendor lock-in is the opposite of engineering freedom.

- Self-hosted — runs on your hardware with Docker
- Your API keys — pay DeepSeek/OpenAI directly, not a middleman
- Your data — no telemetry, no external calls except to your LLM providers
- MIT license — fork it, modify it, use it commercially

## Quick Start

```bash
git clone https://github.com/yourname/aicom
cd aicom
cp .env.example .env  # add your API keys
docker compose up --build -d
```

That's it. Open `http://localhost:9080` and you have a full admin panel.

## What's Next

- More domain-specific methodology packs
- Better chat UX for the new product flow
- Community-contributed agent templates
- Kubernetes-native deployment

## Links

- **GitHub**: [github.com/alexandr/aicom](https://github.com/alexandr/aicom) (MIT)  <!-- вставь свою ссылку -->
- **Docs**: See the `docs/` folder in the repo
- **Demo**: `./demo.sh "SaaS for managing remote teams"` — one command

---

*Built with Python, TypeScript, and way too much coffee. Questions? Drop them in the comments.*
