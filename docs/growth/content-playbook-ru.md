# Плейбук контента — лендинги, README и доки

> 🌐 Языки: [English](./content-playbook.md) · **Русский** · [Español](./content-playbook-es.md) · [Français](./content-playbook-fr.md) · [中文](./content-playbook-zh.md)

Плейбук для агентов и людей, которые работают с репозиториями экосистемы AICOM.

**Публичный контент — на английском.** Русский — только если есть явная RU-версия (как `README-ru.md` у DIOSCURI) — а не примешивается к основному README или лендингу.

**См. также:** [THEOXENIA content plan (EN)](https://github.com/alexar76/dioscuri/blob/main/docs/content-plan.md) · [seeding playbook (EN)](./seeding-playbook.md) · [knowledge base](../ecosystem/knowledge-base-ru.md)

---

## 1. Канонические ссылки (одни на всех)

Все репо должны ссылаться на одни и те же URL. DIOSCURI читает их из `dioscuri.config.json` → `links`; чужие инвайты модерация режет.

| Что | URL (production) | Куда вести |
|-----|------------------|------------|
| Telegram bot (Castor) | https://t.me/next_agent_market_bot | Q&A — спросить близнеца |
| Telegram channel (Castor) | https://t.me/just_for_agents | Новости, релизы, дайджесты |
| Discord (Pollux) | https://discord.gg/aimarket | обсуждения, help, show-and-tell |
| Экосистема | https://magic-ai-factory.com | главный сайт |
| Зеркало / dev | https://modeldev.modelmarket.dev | демо, staging |
| Observatory | https://magic-ai-factory.com/monitor/ | живой статус всего |
| GitHub org | https://github.com/alexar76 | код |
| DIOSCURI | https://github.com/alexar76/dioscuri | близнецы, setup |
| THEOROS canon | https://alexar76.github.io/theoros/ | Agent Sovereignty Canon · `#the-canon` в Discord |
| THEOROS repo | https://github.com/alexar76/theoros | CANON.md, главы, гранитный лендинг |

**Правило:** не придумывать свои Discord/Telegram-инвайты. Если нужен второй канал — сначала согласовать и прописать в `links` у DIOSCURI.

---

## 2. Две двери — две аудитории

Не один универсальный «join community». Два разных CTA:

| Аудитория | CTA | Copy (EN) |
|-----------|-----|-----------|
| Наблюдатель | Telegram | "Release news and digests — Castor on Telegram" → t.me/just_for_agents |
| Разработчик | Discord | "Discuss, ask, show what you built — Pollux on Discord" → discord.gg/aimarket |

В каждом README/лендинге — оба линка, но **первый зависит от репо**:

| Тип репо | Первым |
|----------|--------|
| SDK / client / widget | Discord (разработчики) |
| demo / monitor / landing | Telegram (витрина) |

---

## 3. Лендинг — обязательные блоки

Минимальный скелет (как у [`landing/index.html`](https://github.com/alexar76/dioscuri/blob/main/landing/index.html) DIOSCURI):

### Hero

- **Eyebrow:** Community · AICOM · MIT (или роль проекта)
- **H1:** имя продукта, без крипто-хайпа
- **Subtitle:** одно предложение — что делает, не какой вы крутые
- **3 CTA:** Demo · GitHub · Community (Telegram + Discord)

### Что это (2–3 абзаца)

Проблема → решение → место в экосистеме (Factory / Oracles / AIMarket / ARGUS). Одна ссылка на Alien Monitor как proof of life.

### Features (3–6 карточек)

Факты, не маркетинговый туман: порты, протоколы, что реально работает сегодня. Ссылка на live demo если есть.

### Community block (обязателен)

> Questions? The DIOSCURI twins answer from synced GitHub docs.
>
> • Telegram (Castor) — fast news: https://t.me/just_for_agents
> • Discord (Pollux) — deep threads: https://discord.gg/aimarket

### Footer

Repository · Setup/Docs · Alien Monitor · AICOM ecosystem · (опционально) Русский README

### Meta / SEO

- `description` — ≤160 символов, конкретика
- `og:title`, `og:description` — те же факты, не другой тон
- `lang="en"` на публичных страницах

---

## 4. README — обязательные секции

### Вверху (после badges)

```markdown
Part of the [AICOM open agent economy](https://magic-ai-factory.com).
**Live demo:** <url> · **Community:** [Telegram](https://t.me/just_for_agents) · [Discord](https://discord.gg/aimarket)
```

### What it does

3–5 буллетов. Каждый — проверяемый факт ("syncs READMEs every 60 min", не "revolutionary AI").

### Quick start

Copy-paste команды. Если demo URL — отдельной строкой сразу после install.

### Demo URLs (критично для MNEMOSYNE)

DIOSCURI парсит README и подтягивает demo-ссылки в гайды и скриншоты. Формат:

```markdown
## Demo
- **Live:** https://modeldev.modelmarket.dev/your-demo/
- **Docs:** https://github.com/alexar76/your-repo/blob/main/docs/setup.md
```

Без demo — явно написать **No public demo yet** (не молчать).

### Related repos

Таблица 3–8 соседних репо экосистемы со ссылками. Помогает близнецам отвечать на «что рядом».

### Community (в конце)

Тот же блок, что на лендинге. Можно добавить:

> Release announcements are syndicated by [KERYX](https://github.com/alexar76/dioscuri#keryx-syndication-post-only) (post-only, no spam automation).

---

## 5. Доки (`docs/`) — правила

| Тип | Имя | Содержание |
|-----|-----|------------|
| Setup | `docs/setup.md` | env vars, ports, первый запуск |
| Usage | `docs/usage.md` | как пользоваться, не как маркетить |
| Architecture | `docs/architecture.md` | диаграммы, границы модулей |
| Security | `docs/security.md` | угрозы и что код реально делает |

В каждом `setup.md`:

- ссылка на community в § «Support / Community»
- ссылка на Alien Monitor если сервис там виден
- без секретов в примерах (`REPLACE_ME`, не реальные токены)

**Кросс-линки:** на dioscuri, aicom, соседние репо — относительные пути внутри org, полные URL снаружи.

---

## 6. Тон и стиль (THEOXENIA charter)

Сверяться с [`docs/content-plan.md`](https://github.com/alexar76/dioscuri/blob/main/docs/content-plan.md):

- English only в публичных постах, лендингах, Discord guides
- Dry, technical, myth-flavored — один Olympus-touch на пост, не больше
- Twins tease each other, never users
- No hype: без revolutionary, game-changer, to the moon, price talk, airdrops
- No emoji walls — emoji как знаки (🔨 digest, ⚒ release), не декор
- Silence beats filler — пустая неделя → нет digest, не выдуманный

Запрещённые корпоративные фразы — см. `styleCharter()` в [`src/personas/index.ts`](https://github.com/alexar76/dioscuri/blob/main/src/personas/index.ts) (если пишете текст, который близнецы будут цитировать — не используйте их).

---

## 7. Что помогает MNEMOSYNE (и близнецам)

README и docs — корм для ботов. Пишите так, чтобы retrieval давал ответ:

- Чёткий H1 = имя проекта
- Первый абзац = одно предложение «X is Y that does Z»
- Секция Demo с рабочим URL (не localhost)
- Секция Related — соседи по экосистеме
- Release notes с точкой в первом предложении (KERYX берёт first sentence для Mastodon/Bluesky)
- Без prompt-injection шуток в README ("ignore previous instructions") — AEGIS вырежет chunk

---

## 8. KERYX / релизы — что писать в release notes

Когда тегаете релиз, KERYX постит автоматически:

```
⚒ your-repo v1.2.3 shipped — Short plain title here
https://github.com/alexar76/your-repo/releases/tag/v1.2.3
Community: discord.gg/aimarket | t.me/just_for_agents
```

Для коллег:

- Первая строка release notes — plain English title, ≤120 символов, с точкой в конце если можно
- Без markdown-стен в начале (`##`, `**`, буллеты) — иначе антиспам на Mastodon ловит мусор
- Mastodon: аккаунт прогревать вручную до API; детали — [`docs/use-cases.md`](https://github.com/alexar76/dioscuri/blob/main/docs/use-cases.md) §9

---

## 9. Чего НЕ писать (red lines)

- Свои `discord.gg/…` / `t.me/…` инвайты (модерация = delete)
- «Join for airdrop / whitelist / pump»
- Покупной трафик, join4join, auto-bump DISBOARD
- Секреты в README, docs, лендингах
- Обещания «AI does everything» без ссылки на demo
- Дублирующие setup-посты при каждом деплое (idempotency — дело DIOSCURI, не вашего README)

---

## 10. Чеклист перед merge

- [ ] Hero: что делает + demo + GitHub + community (TG + Discord)
- [ ] Demo URL в README (рабочий, не 502)
- [ ] Related repos — 3+ соседа
- [ ] Публичный текст на английском
- [ ] Канонические community links (не свои инвайты)
- [ ] Release notes: первая строка plain, короткая
- [ ] Нет секретов, нет hype, нет injection-шуток в docs
- [ ] Ссылка на Alien Monitor если проект там живёт

---

## 11. Шаблон copy-paste (README community block)

```markdown
## Community

The [DIOSCURI](https://github.com/alexar76/dioscuri) twins answer questions from synced GitHub docs.

| Channel | Twin | Best for |
|---------|------|----------|
| [Telegram](https://t.me/just_for_agents) | Castor | Releases, digests, quick news |
| [Discord](https://discord.gg/aimarket) | Pollux | Help, ideas, show-and-tell |

**Ecosystem map:** [Alien Monitor](https://magic-ai-factory.com/monitor/) · [AICOM](https://magic-ai-factory.com)
```

---

## 12. Шаблон copy-paste (лендинг CTA row)

```html
<a href="https://t.me/just_for_agents">Telegram · Castor</a>
<a href="https://discord.gg/aimarket">Discord · Pollux</a>
<a href="https://github.com/alexar76/YOUR_REPO">GitHub</a>
<a href="YOUR_DEMO_URL">Live demo</a>
```

---

## 13. Шаблон copy-paste — кнопки «Ask the twins»

Основные CTA на лендингах — ссылки на живые каналы, не `#` якоря и не setup docs:

```html
<a href="https://t.me/next_agent_market_bot">Ask Castor · Telegram</a>
<a href="https://discord.gg/aimarket">Ask Pollux · Discord</a>
```

На **demo / monitor / landing** — Telegram первым. На **SDK / client / widget** — Discord первым.

Опциональная вторичная ссылка для операторов, которые сами хостят близнецов: `Deploy your twins` → `docs/setup.md`.

---

## 14. Трансляция на YouTube (HELIOS)

Загрузка видео — это **больше не** ручной `upload_youtube.py`, используйте [HELIOS](https://github.com/alexar76/helios/blob/main/README.md):

| Шаг | Команда |
|-----|---------|
| Пакетный backfill | `helios backfill-enqueue -n 10`, затем `helios worker` |
| Approve | Просмотреть приватное в Studio → `helios approve JOB_ID` |
| Short под новый релиз | `helios enqueue --template release-short --repo REPO --tag TAG` |
| Редакторский разведчик | Автоматически на `helios worker` (cron) — или `helios calliope run-editorial` |

### Темп роста (канал @My-AI-Factory)

| Фаза | Загрузки | Публичный темп | Микс |
|------|----------|----------------|------|
| **Backfill сейчас** | до 9/день приватно | approve пачками | бэклог PromoMaterials E10+ |
| **Ровный режим** | 1 скрипт CALLIOPE за прогон разведчика | **2–4 публичных/неделю** | вечнозелёные объяснялки + глубокие разборы репо |
| **Релизы** | DIOSCURI `release-short` по тегу | бонус | отгружать новости, когда экосистема тегает |
| **Ручной гейт** | всегда сначала приватно | никогда не авто-публично | Studio + `helios approve` |

Редакторский конфиг (`helios.config.yaml` → `calliope`):

- `scout_interval_days: 3` — ~2 прогона разведчика/неделю, идеи пишутся в `data/editorial/scout_log.jsonl`
- `weekly_enqueue_quota: 3` — качество важнее объёма
- `backfill_pause_threshold: 8` — не конкурировать с загрузками из бэклога

**Устав:** сначала приватно, только шаблонная озвучка для backfill, скрипты нового контента на основе MNEMOSYNE, никакой автоматизации вовлечения. Узел Monitor показывает кэшированную статистику YouTube.

---

## Итог

Лендинг и README — не реклама, а **карта входа**: demo → код → два community-канала → экосистема на Monitor. Один голос, одни ссылки, факты из репо. Близнецы и KERYX сделают остальное сами, если вы им нормальный README оставите.
