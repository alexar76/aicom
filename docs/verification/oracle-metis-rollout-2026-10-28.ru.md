# Обновление Oracle Gateway и METIS 28 октября 2026

Production обновлён без GitHub: **Oracle Gateway 0.3.3 в пяти Hub-контейнерах и METIS 0.2.6 на двух узлах**. Замена завершена в 20:26:11 МСК. Независимая проверка после замены подтвердила `healthy` у всех семи контейнеров, сохранение действующих env, mounts, портов, команды запуска и restart policy.

**Публикация в PyPI остаётся незавершённой:** доступного токена нет. Новые версии собраны и установлены в production из проверенных локальных wheel. На 20:27 МСК PyPI возвращал 404 для 0.3.3 и 0.2.6; установка этих версий из публичного индекса ещё невозможна.

## Production

| Компонент | SSH узел | Контейнер | Было | Стало |
| --- | --- | --- | --- | --- |
| Oracle Gateway | factory-vps | modelmarket-hub | 0.3.1 | 0.3.3 |
| Oracle Gateway | factory-vps | modelmarket-hub-uni | 0.3.1 | 0.3.3 |
| Oracle Gateway | admin-vps | ecosystem-aimarket-hub-1 | 0.3.0 | 0.3.3 |
| Oracle Gateway | competing-lab | modelmarket-hub | 0.3.1 | 0.3.3 |
| Oracle Gateway | competing-lab | signal-hunt-hub-1 | 0.3.1 | 0.3.3 |
| METIS | skopos.modelmarket.dev | metis | 0.2.2 | 0.2.6 |
| METIS | attested | metis-appeal | 0.2.2 | 0.2.6 |

Hub-образы получены узким слоем из прежних immutable images: заменён только Oracle wheel. Проверка writable layers старых контейнеров не обнаружила потерянных изменений исходного кода Hub. Действующие настройки оплаты сохранены, включая последние значения повторяющихся переменных Factory Hub. Адреса сетевых интерфейсов сохранены.

METIS импортирует 0.2.6 из `site-packages`: прежняя копия `/app/metis`, перекрывавшая установленный пакет, удалена в новых образах. Основной узел сохранил **143 записи знаний**, appeal — **0**. На обоих узлах `/v1/models` отвечает 200 с действующим ключом и 401 без ключа или с неверным ключом. Общий nginx и TLS не менялись.

У Signal Hunt внешний PostgreSQL. Полный второй Hub не запускался рядом с production БД: его предварительная проверка включает изолированный MCP-процесс, зависимости, пакет и сравнение конфигурации. После остановки старого Hub новый запущен с прежними настройками PostgreSQL и прошёл HTTP/package/network проверки. Административный Hub проверен через его существующий loopback-порт; отдельный публичный адрес для него не публиковался.

[Независимый аудит семи контейнеров](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/production-audit.json), [METIS receipt](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/prod-metis/receipt.json), [публичные маршруты](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/live/after-routes.json).

## Проверки после обновления

В 20:27 МСК создано новое совместное окружение и установлены оба frozen wheel; зависимости получены из PyPI. `pip check` подтвердил совместимость **39 пакетов**. Это повторная установка локальных release-артефактов, а не установка опубликованных новых версий из PyPI.

- Oracle 0.3.3: настоящий stdio lifecycle, **36 инструментов и 36 корректных схем**, каталог и **пять сценариев бюджета и маршрутизации** прошли.
- METIS 0.2.6: четыре встроенных датасета, запрет mock без opt-in, **20 offline-прогонов** и **шесть HTTP/auth проверок** прошли. Это проверка исполнения, а не оценка качества LLM.
- **Девять публичных MCP endpoints** прошли SDK initialize и tools/list; шесть безопасных поисковых или локальных вызовов успешны.
- Бесплатный GAIA resolve через production MCP вернул Kraków, PL, geonameid 3094802 при `max_price_usd=0`.
- Публичный Platon MCP-вызов с лимитом 0 вернул успешный бесплатный результат с `price_usd=0`. Прямой запрос к Hub без trial-заголовка отклонён с **409 price_limit_exceeded**, maximum 0 и current price 0.01. Первоначальное ожидание теста, что любой MCP-вызов обязан получить 409, исправлено: бесплатное выполнение не нарушает нулевой лимит.

До rollout прошли 56 Oracle-тестов, 30 METIS-тестов, проверки wheel/sdist, Twine и содержимого архивов. Docker builder METIS подтвердил наличие benchmark, mock provider и четырёх датасетов.

[Чистая установка после rollout](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/postdeploy-install/receipt.json), [девять MCP-сессий](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/live/remote-mcp-results.json), [бесплатный GAIA](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/live/free-route-result.json), [нулевой ценовой лимит](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/live/oracle-zero-price-result.json).

Платный Oracle fulfillment, коммерческая генерация METIS и финансовые операции не проверены. Для direct-oracle подтверждена только постпроверка расходов; атомарный ceiling относится к маршруту Hub. Строгий quote/tolerance ceiling может отклонить округлённую до цента цену Hub.

## PyPI и реестр MCP

Готовы wheel и sdist Oracle 0.3.3 и METIS 0.2.6. Их SHA256 зафиксированы в [Oracle manifest](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/oracle/artifacts.json) и [METIS manifest](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/metis/artifacts.json). Скрипты публикации и последующей чистой установки из PyPI подготовлены. Для завершения нужен путь к существующему файлу с PyPI-токеном; сам токен не следует передавать в чат.

Официальный MCP Registry также не обновлён: сохранённый credential namespace `io.github.alexar76` просрочен, refresh credential отсутствует. GitHub login, переключение аккаунта и публикация через GitHub не выполнялись.

## Откат и повторное создание контейнеров

Старые контейнеры остановлены и сохранены под именами с `rollback`; старые immutable images и защищённые резервные копии локальных RW mounts сохранены на соответствующих узлах. Секреты и полные inspect-записи остаются только в remote-каталогах с правами 0700/0600. Резервные копии локальных mounts Signal Hunt не являются резервной копией внешнего PostgreSQL.

У Oracle rollback выполняется remote helper `rollout.py rollback SSH-alias/container` из `/root/oracle-gateway-rollout-20261028`. Для METIS точные пути и команды находятся в [receipt](/Users/alex/Desktop/ai_tests/aicompany/aicom/artifacts/oracle-metis-rollout-2026-10-28/prod-metis/receipt.md).

При ручном пересоздании использовать новые image IDs из receipts и сохранённую конфигурацию. Старые compose/build tags автоматически не переписаны и могут вернуть прежний пакет. Для METIS обязателен действующий API command `metis-serve --host 0.0.0.0 --port 8080 --config /app/config/prod.yaml`: у базового image default command остаётся coordinator.

GitHub writes, публикаций кода, смены аккаунтов и реальных платежей не было. Изменения PingBlip не затрагивались.
