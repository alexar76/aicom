# FAQ (русский)

> Полные ответы: [`docs/FAQ.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.ru.md)  
> Подробное руководство: [`docs/USER_GUIDE.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.ru.md)

## Что такое AI-Factory?

Система на **вашем сервере**: цепочка LLM-агентов от идеи до лендинга или full-stack приложения с QA, безопасностью и выкладкой.

## Витрина и админка — в чём разница?

| Место | Что показывает |
|-------|----------------|
| Главная `/` | Только готовые к показу продукты |
| **Admin → Pipeline** | Все `prod-…`, этапы, ошибки, ремонт |

**Completed** на дашборде ≠ всегда карточка на витрине.

## Пароль по умолчанию?

В репозитории **нет**. Первый запуск: консоль или `data/secrets/bootstrap_admin.txt`.  
На демо **magic-ai-factory.com** — `admin` / `demo123` (только этот хост).

## Сколько ждать продукт?

- **marketing_landing** — часто 20–25 минут  
- **full_software** — от ~25 минут до нескольких часов при повторных гейтах  

## Почему продукт в ремонте?

Провал гейта (демо/TZ, браузер, security, методолог). Статусы `BUG_FOUND` → `DEV_FIXING`. Смотрите вкладки **Pipeline** и **LLM Logs**.

## Зачем `AIFACTORY_GATE_FAILING_MODEL`?

Жёсткая модель **того же провайдера** только на раундах починки после провала QA. Провайдер не меняется.

## Зачем `AIFACTORY_MAX_QUALITY_LOOPS`?

Лимит циклов policy audit / remediation (по умолчанию **8**), потом **FAILED**.

## Discovery не создаёт идеи?

Проверьте расписание Director, ключи API для Reddit/HN/GitHub, `data/discovery/source_health.json`, ручной запуск: `POST /api/admin/discovery/run`.

## Пустые вкладки LLM / Providers?

Перелогиньтесь (протухший cookie). У роли `viewer` часть API только на чтение — для правок нужен `operator`+.

## Документация на английском

Техническая база в `docs/` — EN. RU: FAQ и USER_GUIDE выше. Wiki EN: [[FAQ]] · [[Home]]
