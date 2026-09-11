## DIOSCURI v0.1.0

**Twin community agents for the AICOM ecosystem**

- **CASTOR** — Telegram (grammY long-polling)
- **POLLUX** — Discord (discord.js gateway)
- **MNEMOSYNE** — self-syncing knowledge base from the AICOM GitHub org
- **AEGIS** — prompt-injection firewall and moderation shield
- **THEOXENIA** — content calendar (spotlights, digests, cross-platform banter)
- **DRY-RUN** — `DIOSCURI_DRY_RUN=1` boots without platform tokens (CI-friendly)

### Install

```bash
npm install -g @alexar76/dioscuri
cp dioscuri.config.example.json dioscuri.config.json
cp .env.example .env   # add secrets
dioscuri
```

Or Docker: see [README](https://github.com/alexar76/dioscuri#quick-start-docker).

**Landing:** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/)
