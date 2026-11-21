# Production moved from MiniMax to Qwen on OpenRouter, 2026-11-21

Owner 2026-11-21, after OpenRouter's notice that requests to MiniMax models may have been read by a third party:
move every production service from `minimax/minimax-m3` to the newest Qwen. Model: `qwen/qwen4-max` (OpenRouter
price list read the same day: $1.425 in / $4.275 out per 1M tokens; MiniMax-M3 was $0.30 / $1.20). Times are UTC
from the hosts' clocks. A direct test call with the Factory's key returned in 2 s, served by Alibaba.

| Host | Service | What changed | When | Rollback |
|---|---|---|---|---|
| factory-vps | Factory `aicom-app-1` | `data/config/model_providers.yaml`: heavy and light model of `openrouter_api`; new `data/config/llm_pricing.yaml` with the Qwen price; container restarted twice | 09:05:23, 09:22 | `/root/llm-qwen-20261121/model_providers.yaml.before`, restart |
| factory-vps | `alien-monitor`, `alien-monitor-live` | read the Factory's provider file; restarted | 09:06 | same file |
| factory-vps | `aicom-diagnostics` | `DIAGNOSIS_MODEL` (container replaced) | 09:07:40 | `aicom-diagnostics-security-prev-1795252060485093718` |
| factory-vps | `modelmarket-hub` (+ THEMIS in its namespace) | `AIMARKET_FEDERATION_JUDGE_MODEL` set (was the code default) | 09:17:40 | `modelmarket-hub-security-prev-1795252660844371447` |
| skopos-vps | Metis | `/opt/metis/deploy/prod.yaml`: base model, 13 seats, 1 jury seat (15 places); Qwen price added; restarted | 09:09:31 | `/root/llm-qwen-20261121/prod.yaml.before` |
| skopos-vps | SKOPOS agent `metis-skopos` | `/opt/skopos-test/deploy/agent.yaml`; restarted | 09:09:57 | `skopos-agent.yaml.before` |
| admin-vps | `momus-backend`, `momus-treasury`, `momus-verifier` | `MOMUS_LLM_MODEL` (containers replaced); `/root/momus-deploy/.env` and compose defaults | 09:10:45–09:10:52 | `*-security-prev-17952522*`, `momus.env.before`, `momus-compose.before` |
| admin-vps | `dioscuri` | five model variables (container replaced); `/root/dioscuri/.env` | 09:16:48 | `dioscuri-security-prev-1795252494124734263`, `dioscuri.env.before` |
| attested | `attested-memory-hub-hub-1` | `AIMARKET_FEDERATION_JUDGE_MODEL` (container replaced, after the 3.22.0 rollout of another session); compose `.env` | 09:20:29 | previous container kept, `attested-hub.env.before` |
| attested | HELIOS | `/root/helios/.env` only | 09:18 | `helios.env.before` |
| indep | hub, Dayslap | `/etc/independentai/hub.env`, `dayslap.env`; both services restarted | 09:08:44 | `/root/llm-qwen-20261121/*.before` |

Each host keeps its files in `/root/llm-qwen-20261121/` (created by this change).

## Light roles on qwen3.8-flash (owner, same day)

Owner: «да, лёгкие на flash». `qwen/qwen3.8-flash` costs $0.15 / $0.47 per 1M tokens (same price list).

| Host | Service | What changed | When | Rollback |
|---|---|---|---|---|
| factory-vps | Factory light slot (market research, QA, PM, marketing, sales, devops, critics); the monitors read the same file | `light:` in `model_providers.yaml`, price added; app and both monitors restarted | 09:27:38 | `model_providers.yaml.before-flash` |
| indep | Dayslap | `OPENROUTER_MODEL`; restarted | 09:28:11 | `dayslap.env.before-flash` |
| skopos-vps | SKOPOS agent | `agent.yaml`; restarted | 09:28:19 | `skopos-agent.yaml.before-flash` |

After: two calls through the Factory router at 09:28 are in `llm_calls.jsonl`: `pm_analysis` light on
`qwen/qwen3.8-flash` and `architecture_design` heavy on `qwen/qwen4-max`, both success. Heavy roles (code generation,
architecture, security scan), Metis, MOMUS, DIOSCURI, diagnostics and the hub judges stay on `qwen/qwen4-max`.
No Dayslap card and no SKOPOS agent answer was produced after the switch.

## Checked after

- No running container on factory-vps, admin-vps, competing-lab or skopos-vps has `minimax` in its environment.
- Factory: one call through its own router at 09:21:35 is in `llm_calls.jsonl` as `openrouter_api qwen/qwen4-max`,
  success.
- MOMUS `/health`: provider model `qwen/qwen4-max`, reachable. Metis, both hubs, THEMIS, DIOSCURI, diagnostics,
  SKOPOS agent, both monitors: healthy.

## Not done, and limits

- `helios` and `helios-worker` (attested) still carry four unused MiniMax variables in their environment; HELIOS's
  own model is DeepSeek. The file is changed; the containers were not restarted (they render and publish videos).
- The first DIOSCURI replacement was rolled back by the tool: DIOSCURI answers `/health` only ~2.5 minutes after
  start, the tool waits 90 s. The second run used a 420 s wait. DIOSCURI was down for about five minutes in total.
- The hubs on competing-lab already judged with DeepSeek; nothing changed there. `modelmarket-hub-uni` has no judge key.
- Metis knows no capability score for `qwen4-max` and uses its default (65; MiniMax-M3 had 92), so its role gating
  gives the high-leverage roles to other models. No Metis verdict was requested after the switch.
- No Metis, MOMUS, DIOSCURI, diagnostics or hub-judge call to the model was made after the switch.
- The apex and Attested hub containers now show their image by id, not by the `3.22.0-20261121` tag (same image).
- During the survey one hub peer key (`AIMARKET_PEER_API_KEYS`, hub → HESTIA) was printed into the session log by
  a too-narrow mask. It left no other place.
- Repository defaults (`aimarket-hub` judge default, Factory OpenRouter defaults, examples, fleet scripts) are
  changed in the same commit; the hub default reaches production with the next hub release.
