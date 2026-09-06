# Аварийный failover LLM — отказ DeepSeek → OpenRouter (MiniMax + Kimi K3)

Когда **DeepSeek** недоступен, не проходит оплата или ключи перестали работать, экосистему можно перевести на **OpenRouter** за минуты без ручной правки каждого сервиса.

## Когда применять

- Ошибки оплаты / квоты / outage DeepSeek на Factory, Metis, ATLAS, MOMUS и т.д.
- Нужен **рабочий** облачный маршрут, пока чинится биллинг DeepSeek.
- Нужна **мягкая пауза фабрики**, чтобы автономный пайплайн не усугублял сбой.

## Что делает скрипт

`./scripts/failover_openrouter_minimax.sh` (или `python3 scripts/llm_failover_openrouter.py apply`):

| Цель | Действие |
|------|----------|
| **Factory** | `factory_on_hold: true`; провайдер `openrouter_api` по умолчанию; ключ в `data/secrets/llm/openrouter_api_key` |
| **Alien Monitor** | Тот же `model_providers.yaml` |
| **ATLAS** | `.env`: `ATLAS_LLM_*` → OpenRouter + `minimax/minimax-m3` |
| **Metis** | `prod.yaml`: base → MiniMax; все DeepSeek-слоты → OpenRouter; **`intent_parser_c` → `moonshotai/kimi-k3`** |
| **SKOPOS** | Уже OpenRouter в `agent.example.yaml` — нужен `OPENROUTER_API_KEY` |

Модели:

- **MiniMax-M3** — `minimax/minimax-m3` (Factory + большинство слотов Metis)
- **Kimi K3** — `moonshotai/kimi-k3` (диверсификатор `intent_parser_c` в Metis)

## Быстрый запуск

```bash
./scripts/failover_openrouter_minimax.sh --from-metis-env
```

Ключ берётся из `/opt/metis/.env`, патчится Metis и factory-хост, фабрика ставится на hold. Перезапуск: `aicom-app-1`, `atlas-atlas-1`, `alien-monitor`, `metis`.

## Проверка

```bash
python3 scripts/pipeline_focus_status.py
ssh root@skopos.modelmarket.dev "grep -E '^(base_model|api_key_env):' /opt/metis/deploy/prod.yaml"
```

## Вернуть DeepSeek

1. Admin → Settings → снять hold.
2. Восстановить `*.bak-*` у `prod.yaml` и `model_providers.yaml`.
3. Убрать блок `# llm_failover_openrouter` из `.env` на factory.
4. `docker restart metis aicom-app-1 atlas-atlas-1 alien-monitor`

Подробности (EN): [llm-failover-openrouter.md](llm-failover-openrouter.md)
