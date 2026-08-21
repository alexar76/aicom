# Competing Hub VPS — галактика лабораторной федерации
#
# Языки: [EN](hub-vps-competing.md) · [RU](hub-vps-competing-ru.md) · [ES](hub-vps-competing-es.md) · [FR](hub-vps-competing-fr.md) · [ZH](hub-vps-competing-zh.md)
#
# Хост: `hunt.modelmarket.dev` (Timeweb)
# DNS: `hunt.modelmarket.dev` → этот IP · `hub.modelmarket.dev` · `use.modelmarket.dev`

Ранбук второго Hub-а, который primary-федерация (`https://modelmarket.dev`) обнаруживает,
плюс Signal Hunt и портал use-cases на той же машине. Это **не** `./start.sh --everything`
(нужно ≥16 GB RAM; здесь ~8 GB + swap).

## Критерий готовности

| Поверхность | URL | Роль |
|-------------|-----|------|
| Competing Lab Hub | `http://hunt.modelmarket.dev:9083` | UNI-only пир primary |
| Signal Hunt | `https://hunt.modelmarket.dev` | Игра + свой Hub за nginx |
| Use-cases | `use.modelmarket.dev` | Статический портал |
| Alien Monitor | primary | Вторая **галактика** далеко от origin |

Федерация **не** автоматическая — нужны скрипты ниже.

## Скрипты

| Скрипт | Назначение |
|--------|------------|
| [`scripts/register_hub_upstream.sh`](../../scripts/register_hub_upstream.sh) | Один пир: announce → approve → crawl |
| [`scripts/register_federation_mesh.sh`](../../scripts/register_federation_mesh.sh) | Полный mesh primary ↔ lab ↔ hunt |
| [`signal-hunt/scripts/register-upstream.sh`](https://github.com/alexar76/signal-hunt/blob/main/scripts/register-upstream.sh) | То же + проверка tools Signal Hunt |
| [`scripts/announce-platon-oracles.sh`](../../scripts/announce-platon-oracles.sh) | Platon на локальный Hub |
| [`scripts/verify_federation_urls.py`](../../scripts/verify_federation_urls.py) | Проверка URL / well-known |

Токены только в env процесса — не в git и не в доках.

## Федерация

```bash
# один пир на primary
UPSTREAM_ADMIN_TOKEN='…' ./scripts/register_hub_upstream.sh \
  http://hunt.modelmarket.dev:9083 https://modelmarket.dev
UPSTREAM_ADMIN_TOKEN='…' ./signal-hunt/scripts/register-upstream.sh \
  https://hunt.modelmarket.dev https://modelmarket.dev

# полный mesh
PRIMARY_ADMIN_TOKEN='…' LAB_ADMIN_TOKEN='…' HUNT_ADMIN_TOKEN='…' \
  ./scripts/register_federation_mesh.sh
```

Шаги: `announce` → `peers/approve` (`trusted: true`) → `crawl`.  
Новые capabilities появляются только если lab публикует **свои** tools (например `signal.*@v1`), а не копию тех же оракулов.

## Alien Monitor

```bash
ALIEN_COMPETING_HUB_URL=http://hunt.modelmarket.dev:9083
ALIEN_SIGNAL_HUNT_URL=https://hunt.modelmarket.dev
ALIEN_USE_CASES_URL=https://use.modelmarket.dev
```

Якорь: `COMPETING_GALAXY_ANCHOR ≈ (30, 12, −20)` — далеко от хаба `(0,0,0)`.  
Узлы: `competing_hub`, `signal_hunt`, `use_cases`.

Полный EN-ранбук: [hub-vps-competing.md](hub-vps-competing.md).
