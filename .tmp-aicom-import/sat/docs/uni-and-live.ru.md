# UNI и LIVE — два мира

> **English:** [uni-and-live.md](./uni-and-live.md) · **Русский** · **Español:** [uni-and-live.es.md](./uni-and-live.es.md) · **Français:** [uni-and-live.fr.md](./uni-and-live.fr.md) · **中文:** [uni-and-live.zh.md](./uni-and-live.zh.md)

Два процесса, два хаба, два каталога. Смешать их — значит принять пузырьковые доллары за
выручку.

Эта страница — **UNI против LIVE**. TEST — третья накладка на тот же процесс монитора, не
третья экономика. Ончейн-переключатель: [crypto-switch.ru.md](./crypto-switch.ru.md). Печать
UNI: [uni-realm.md](./uni-realm.md).

## Сводка

| | **LIVE** | **UNI** |
|---|---|---|
| Хаб | [modelmarket.dev](https://modelmarket.dev) | [uni.modelmarket.dev](https://uni.modelmarket.dev) |
| Alien Monitor | [`monitor.modelmarket.dev`](https://monitor.modelmarket.dev/) · `:9101` · `ALIEN_MODE=real` | [monitor-uni.modelmarket.dev](https://monitor-uni.modelmarket.dev/) · `:9100` · `ALIEN_MODE=universe` |
| Деньги | Base, когда крипто **включено** | свой Anvil, chain id `31337` — симуляция |
| Каталог | живая федерация (Platon, ATLAS, GAIA, оракулы, …) | шесть лабораторий пузыря ниже |
| Эти шесть лабораторий | **не** пиры LIVE-федерации | KHRONOS · STOICHEION · HORIZON · PSEPHOS · KYMA · DIKTYON |
| Деплой хаба | `./scripts/deploy_hub.sh` | `bash deploy/uni-hub.sh …` |
| Деплой возможностей | живые спутники | `bash deploy/uni-satellites.sh` |
| Деплой монитора | `ALIEN_MODE=real ./scripts/deploy_alien_monitor.sh --live` | `./scripts/deploy_alien_monitor.sh` (universe) |

Бейдж LIVE на карте вселенной — это не живые деньги. Кнопки **переходят** между картами,
а не перекрашивают один процесс.

## LIVE

Что поднимаете: настоящую экономику.

- **Хаб** отвечает на `https://modelmarket.dev`. Локальных возможностей ноль; каталог —
  федерация с живых спутников.
- **Монитор** — второй контейнер (`alien-monitor-live`). CTA карточки и опрос статистики
  идут в этот хаб. Кнопка LIVE остаётся. Кнопка UNI ведёт на `/monitor/`.
- **Шары:** живые спутники и чужаки. Шесть UNI-лабораторий **не** пиры каталога.
- **Крипто** — отдельный переключатель. LIVE с крипто **выкл** всё равно говорит с живым
  хабом; узлы цепочки не загораются. См. [crypto-switch.ru.md](./crypto-switch.ru.md).

## UNI

Что поднимаете: герметичную параллельную экономику. Изнутри API выглядят как LIVE. Имя —
печать: отдельный поддомен, никогда путь под живым хостом.

- **Хаб** отвечает на `https://uni.modelmarket.dev` (loopback `:9183` за nginx).
- **Монитор** — процесс вселенной по умолчанию. CTA и опрос статистики —
  `ALIEN_UNI_HUB_URL` / `https://uni.modelmarket.dev`, **не** живой хаб. Кнопка UNI
  остаётся. Кнопка LIVE ведёт на `/monitor-live/`.
- **Пиры каталога** — шесть лабораторий только для пузыря: один процесс
  (`uni/satellite.py`) × шесть каталогов, поднимает `deploy/uni-satellites.sh`. Пути под
  именем UNI-хаба, чтобы SSRF-страж краулера их принял. Ключи в `/var/lib/uni-satellites`
  должны пережить редеплой: хаб пинит ключ пира при первом контакте.

| спутник | продукт | caps | продаёт |
|---|---|---|---|
| KHRONOS Time Series | `khronos` | 20 | статистика, сглаживание, декомпозиция, прогноз |
| STOICHEION Data Hygiene | `stoicheion` | 17 | схемы, диффы, профили, текст, единицы |
| HORIZON Geo & Telemetry | `horizon` | 17 | геодезия, пространственные запросы, телеметрия |
| PSEPHOS Draws & Ballots | `psephos` | 13 | жеребьёвки с commitment, дискретная вероятность, бюллетени |
| KYMA Signal Lab | `kyma` | 12 | спектры, фильтры, волны |
| DIKTYON Graph Metrics | `diktyon` | 12 | центральность, связность, порядок |

Каждая возможность — чистая функция входа на стандартной библиотеке. Симулируются только
деньги. Подробности: [uni/README.md](../uni/README.md).

**Обзорная палуба.** Platon, ATLAS и прочие живые спутники могут быть на UNI-карте как
оверлей статуса **живых** сервисов. Это не пиры UNI-каталога. Пиры каталога — шесть
лабораторий.

## Не смешивать

| Утечка | Что происходит |
|---|---|
| UNI-монитор опрашивает живой хаб | на обеих картах одни и те же invoke / доллары |
| CTA карточки UNI — `modelmarket.dev` | оператору внутри пузыря дают дверь наружу |
| LIVE seed-лист в UNI-хабе | пузырь публикует адреса живых спутников и может провести живые деньги |
| Покраска `mode=real` на UNI-процессе | цифры на экране всё ещё пузыря |

Печать хаба (`aimarket_hub/realm.py`) отказывает живому seed внутри UNI и приватному seed
внутри LIVE. Монитор (`session_tick_mode`) не тикает чужие числа на этом процессе.

## Связанное

- [uni-realm.md](./uni-realm.md) — печать цепи, Anvil, почему пузырь в production-режиме
- [crypto-switch.ru.md](./crypto-switch.ru.md) — ончейн вкл/выкл (это не UNI)
- [alien-monitor-factory-catalog.ru.md](./alien-monitor-factory-catalog.ru.md) — кластеры Factory на обеих картах
- [quickstart-ecosystem-deploy.ru.md](./quickstart-ecosystem-deploy.ru.md) — живой флот
