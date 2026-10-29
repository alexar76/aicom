# aimarket-agents

Чистый Python, без n8n. Два независимых сервиса плюс общий модуль:

- `agent4_lead_qualifier/` - квалификация лидов по скрипту из 6 пунктов, запись в Google Sheets, реф-ссылка по завершении. Два режима запуска, логика квалификации одна и та же:
  - `bot.py` - официальный Telegram-бот через Bot API (токен от @BotFather).
  - `userbot.py` - работает внутри личного Telegram-аккаунта: отвечает только на входящие личные сообщения, никогда не пишет первым. Для случая, когда первое сообщение вручную отправляет реальный человек с личного аккаунта, а квалификацию дальше ведёт бот. Требует `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` (свои, с https://my.telegram.org) и один интерактивный вход при первом запуске (см. docstring в файле).
- `agent5_marketing_analytics/` - синк метрик Яндекс.Директ и VK Ads в Postgres, еженедельный отчёт руководителю в Telegram, Q&A-бот по метрикам.
- `common/` - настройки (`.env`) и провайдер-независимый LLM-клиент, общие для обоих агентов.

Каждый модуль - обычный процесс, который запускается одной командой и живёт под systemd, ничего общего с другими проектами на сервере (свой venv, свой `.env`, свои логи через journalctl).

## Установка

```bash
cd aimarket-agents
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполнить .env: токены ботов, ключ LLM, Google Sheets, Postgres, Яндекс.Директ/VK Ads
```

Для Google Sheets: создать сервисный аккаунт в Google Cloud, скачать JSON-ключ, положить рядом (путь указан в `GOOGLE_SERVICE_ACCOUNT_FILE`), открыть доступ к таблице для email сервисного аккаунта (роль "Редактор"). В таблице должны быть две вкладки:

- **Leads**: `created_at, channel, chat_id, username, contact, role, marketplaces, category, experience, turnover, team_size, pain_points, referral_link`
- **Links**: `channel, referral_link` - это админ-панель без кода: строка `channel=telegram` с реальной ссылкой. Чтобы добавить канал (avito, max, instagram), просто добавьте новую строку - код менять не нужно.

Схема Postgres (`agent5_marketing_analytics/schema.sql`) применяется автоматически при первом запуске синка или планировщика (`CREATE TABLE IF NOT EXISTS`), руками выполнять не обязательно.

## Проверка без единого ключа (офлайн-демо)

Никакие реальные credentials для этого не нужны - ни токен бота, ни LLM-ключ, ни Postgres, ни Google, ни Яндекс.Директ/VK Ads. Всё подменено фейками (`tests/fakes.py`): фейковый LLM отвечает заранее заданными репликами, фейковая Google-таблица и фейковый Postgres просто держат данные в памяти процесса.

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
python scripts/demo_offline.py
```

Скрипт прогоняет по-настоящему всю бизнес-логику (не заглушки внутри самих агентов, а именно `conversation.run_turn`, `sync.run_all`, `weekly_report.generate_weekly_summary`, `qa_bot.answer_question`) и печатает в терминал: полный диалог квалификации лида с итоговой строкой для таблицы, апсерт метрик по обоим каналам, готовую еженедельную сводку с пометкой аномалии и ответ Q&A-бота на вопрос руководителя.

То же самое, но в виде автоматических тестов с проверками (`assert`), а не просто вывода в консоль:

```bash
pytest -v
```

19 тестов: 4 - на чистую логику (парсинг JSON-ответа модели, разбор TSV Яндекс.Директ, нормализация VK Ads, расчёт аномалий и промптов), ещё 4 - end-to-end сценарии для каждого агента целиком (см. `tests/test_agent4_end_to_end.py`, `tests/test_agent5_sync_end_to_end.py`, `tests/test_agent5_weekly_report_end_to_end.py`, `tests/test_agent5_qa_bot_end_to_end.py`), остальные - точечные проверки отдельных функций. Все 17 проходят.

Единственное, что нельзя проверить без реальных ключей - собственно сетевые вызовы к настоящему Telegram/LLM/Яндекс.Директ/VK Ads API (то, ради чего ключи и существуют). Но вся логика вокруг них - разбор ответов, принятие решений, формирование сообщений - уже проверена офлайн.

## Проверка руками (терминал / VS Code)

Каждый файл ниже можно просто запустить и посмотреть, что происходит (для этого уже нужны настоящие ключи в `.env`):

```bash
source venv/bin/activate

# Агент 4: телеграм-бот квалификации, официальный Bot API (Ctrl+C чтобы остановить)
python -m agent4_lead_qualifier.bot

# Агент 4: тот же скрипт, но внутри личного аккаунта (юзербот-режим).
# Первый запуск - интерактивно, спросит номер телефона и код из Telegram.
python -m agent4_lead_qualifier.userbot

# Агент 5: разовый синк метрик за вчера
python -m agent5_marketing_analytics.sync

# Агент 5: сгенерировать и отправить еженедельный отчёт прямо сейчас
python -m agent5_marketing_analytics.weekly_report

# Агент 5: телеграм Q&A-бот
python -m agent5_marketing_analytics.qa_bot

# Агент 5: постоянный процесс с расписанием (синк 06:00, отчёт вс 09:00)
python -m agent5_marketing_analytics.scheduler_service
```

В VS Code то же самое - открыть папку, выбрать интерпретатор `venv/bin/python`, запускать файлы через "Run Python File" или из встроенного терминала теми же командами.

## Деплой на сервере (systemd)

```bash
sudo useradd -r -s /usr/sbin/nologin aimarket   # отдельный системный пользователь
sudo mkdir -p /opt/aimarket-agents
sudo cp -r . /opt/aimarket-agents
cd /opt/aimarket-agents
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt
sudo cp .env.example .env   # и заполнить реальными значениями
sudo chown -R aimarket:aimarket /opt/aimarket-agents

sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aimarket-agent4-bot aimarket-agent5-qa-bot aimarket-agent5-scheduler

# логи:
journalctl -u aimarket-agent4-bot -f
```

Три отдельных сервиса, каждый рестартует сам при падении (`Restart=on-failure`), не требует Docker и не трогает другие проекты на сервере.

Если нужен юзербот-режим Агента 4 (`systemd/aimarket-agent4-userbot.service`) вместо обычного бота: сначала под этим же системным пользователем один раз запустить `python -m agent4_lead_qualifier.userbot` вручную и пройти интерактивный вход (номер телефона, код из Telegram), это создаст файл сессии в `/opt/aimarket-agents`. Только после этого включать сервис через systemd, иначе процессу неоткуда взять код подтверждения и он будет падать в цикл.

## Архитектурные решения и ограничения (MVP)

- **LLM провайдер абстрагирован** (`common/llm.py`): `LLM_PROVIDER=openai` работает с любым OpenAI-совместимым эндпоинтом (OpenAI, DeepSeek, OpenRouter, локальный vLLM), `LLM_PROVIDER=anthropic` - нативный Anthropic Messages API. Смена провайдера - одна переменная в `.env`, код не трогаем.
- **Память диалога Агента 4** сейчас в памяти процесса (`dict` по chat_id). Простое и рабочее решение для одного бота на одном сервере; при перезапуске незавершённые анкеты теряются. Апгрейд: заменить `ConversationSession` хранением в SQLite/Redis по chat_id.
- **Q&A-бот Агента 5** не строит SQL на лету под конкретный вопрос - всегда передаёт LLM один и тот же агрегированный контекст (8 недель метрик, топ-5 проблем клиентов, воронка за 30 дней). Для более гибких ответов на нестандартные вопросы можно заменить на агента с доступом к Postgres как инструменту (text-to-SQL).
- **Порог аномалии** (20%) сейчас константа в `weekly_report.py`. Таблица `anomaly_config` в схеме уже создана для будущей динамической настройки по каналу/метрике.
- **raw_payload** в `ad_metrics_daily` пока не заполняется (зарезервирован под будущий аудит исходных ответов API).
