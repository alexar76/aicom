# Профили LLM-маршрутизации — флот из 4 серверов

Быстрое переключение между **DeepSeek API**, **гибридом Metis** (DeepSeek + MiniMax через OpenRouter) и **аварийным OpenRouter**.

## Четыре сервера

| Хост | SSH | AI-ассистенты |
|------|-----|---------------|
| **Factory** | `my-vps` | Factory, Alien Monitor, ATLAS, ARGUS, THEMIS |
| **Metis** | `root@skopos.modelmarket.dev` | Metis, SKOPOS |
| **Oracles** | `admin-vps` | MOMUS, HELIOS, DIOSCURI, Platon, LOGOS |
| **Hub lab** | `competing-lab` | Hub (verify через Metis) |

## Профили

| Профиль | Смысл |
|---------|--------|
| **`hybrid-metis`** | Норма: везде DeepSeek; в Metis скептики (`intent_parser_b`, `moa_proposer_skeptic`) → MiniMax на OpenRouter |
| **`deepseek-all`** | Всё на api.deepseek.com, снять hold с фабрики |
| **`openrouter-all`** | Авария: OpenRouter MiniMax везде + Kimi-K3 в Metis, фабрика на hold |

```bash
./scripts/switch_llm_profile.sh hybrid-metis      # канон
./scripts/switch_llm_profile.sh deepseek-all      # обратно на DeepSeek
./scripts/switch_llm_profile.sh openrouter-all --from-metis-env
./scripts/switch_llm_profile.sh scan
```

Полная схема (EN): [llm-routing-profiles.md](llm-routing-profiles.md)
